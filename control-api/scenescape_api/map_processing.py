from __future__ import annotations

import math
from pathlib import Path

from fastapi import HTTPException

from .media_files import delete_media, media_path, store_bytes

THUMBNAIL_WIDTH = 1024
THUMBNAIL_HEIGHT = 768


def _require_mesh_stack():
    try:
        import numpy as np
        import trimesh
    except Exception as exc:
        raise HTTPException(503, {'map': ['3D map processing dependencies are unavailable.']}) from exc
    return np, trimesh


def _load_mesh(path: Path):
    np, trimesh = _require_mesh_stack()
    try:
        loaded = trimesh.load(str(path), force='scene')
        mesh = loaded.to_geometry() if hasattr(loaded, 'to_geometry') else loaded
        if not hasattr(mesh, 'vertices') or len(mesh.vertices) == 0:
            raise ValueError('mesh contains no vertices')
        if not hasattr(mesh, 'faces') or len(mesh.faces) == 0:
            raise ValueError('mesh contains no triangle faces')
        return mesh
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(400, {'map': [f'Failed to read 3D map: {exc}']}) from exc


def convert_point_cloud_ply(ply_url: str, scene_name: str) -> str:
    """Port the 2026.2 point-cloud -> Poisson mesh -> GLB behavior.

    Imports are lazy because only PLY uploads require the Open3D stack. The
    native image pins the same Open3D/plyfile/trimesh family used by 2026.2.
    """
    path = media_path(ply_url)
    if path is None or not path.is_file():
        raise HTTPException(400, {'map': ['PLY map file is unavailable.']})
    try:
        import numpy as np
        import open3d as o3d
        import trimesh
        from plyfile import PlyData
    except Exception as exc:
        raise HTTPException(503, {'map': ['PLY conversion dependencies are unavailable.']}) from exc

    try:
        plydata = PlyData.read(str(path))
        vertex_data = plydata['vertex'].data
        points = np.stack([vertex_data['x'], vertex_data['y'], vertex_data['z']], axis=-1)
        # 2026.2 expects diffuse_* colors. Accept the conventional red/green/blue
        # spelling as a non-breaking compatibility extension.
        names = set(vertex_data.dtype.names or ())
        if {'diffuse_red', 'diffuse_green', 'diffuse_blue'} <= names:
            keys = ('diffuse_red', 'diffuse_green', 'diffuse_blue')
        elif {'red', 'green', 'blue'} <= names:
            keys = ('red', 'green', 'blue')
        else:
            raise ValueError('PLY point cloud is missing RGB color properties')
        colors = np.stack([vertex_data[key] for key in keys], axis=-1).astype(np.float32) / 255.0

        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(points)
        pcd.colors = o3d.utility.Vector3dVector(colors)
        pcd = pcd.voxel_down_sample(voxel_size=0.01)
        pcd, _ = pcd.remove_statistical_outlier(nb_neighbors=20, std_ratio=1.5)
        if len(pcd.points) < 4:
            raise ValueError('not enough point-cloud samples after filtering')
        pcd.estimate_normals(search_param=o3d.geometry.KDTreeSearchParamHybrid(radius=0.03, max_nn=100))
        pcd.orient_normals_consistent_tangent_plane(10)
        mesh, densities = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
            pcd, depth=8, linear_fit=True
        )
        densities = np.asarray(densities)
        keep = densities > np.quantile(densities, 0.02)
        mesh = mesh.select_by_index(np.where(keep)[0])
        mesh.remove_degenerate_triangles()
        mesh.remove_duplicated_triangles()
        mesh.remove_non_manifold_edges()
        mesh.compute_vertex_normals()
        mesh = mesh.filter_smooth_taubin(number_of_iterations=5, lambda_filter=0.5, mu=-0.53)
        mesh.compute_vertex_normals()

        pcd_tree = o3d.geometry.KDTreeFlann(pcd)
        pcd_colors = np.asarray(pcd.colors)
        vertex_colors = []
        for vertex in mesh.vertices:
            _, indexes, _ = pcd_tree.search_knn_vector_3d(vertex, 1)
            vertex_colors.append(pcd_colors[indexes[0]])
        tri = trimesh.Trimesh(
            vertices=np.asarray(mesh.vertices),
            faces=np.asarray(mesh.triangles),
            vertex_colors=(np.asarray(vertex_colors) * 255).astype(np.uint8),
            process=False,
        )
        tri.metadata['name'] = 'mesh_0'
        glb = tri.export(file_type='glb')
        url = store_bytes(f'{scene_name}.glb', glb, kind='scene-map')
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(400, {'map': [f'Error processing .ply file: {exc}']}) from exc

    delete_media(ply_url)
    return url


def auto_align_glb(glb_url: str) -> tuple[list[float], list[float]]:
    np, trimesh = _require_mesh_stack()
    path = media_path(glb_url)
    if path is None or not path.is_file():
        raise HTTPException(400, {'map': ['GLB map file is unavailable.']})
    mesh = _load_mesh(path).copy()
    rotation = trimesh.transformations.rotation_matrix(math.radians(90.0), [1.0, 0.0, 0.0])
    mesh.apply_transform(rotation)
    extents = np.asarray(mesh.extents, dtype=float)
    if extents.shape != (3,) or not np.all(np.isfinite(extents)):
        raise HTTPException(400, {'map': ['Unable to determine GLB map dimensions.']})
    return [90.0, 0.0, 0.0], [float(extents[0] / 2), float(extents[1] / 2), float(extents[2] / 2)]


def _mesh_transform(mesh, rotation: list[float], translation: list[float], scale: list[float]):
    np, trimesh = _require_mesh_stack()
    result = mesh.copy()
    scale_matrix = np.eye(4)
    scale_matrix[0, 0], scale_matrix[1, 1], scale_matrix[2, 2] = scale
    result.apply_transform(scale_matrix)
    rx, ry, rz = [math.radians(float(value)) for value in rotation]
    result.apply_transform(trimesh.transformations.euler_matrix(rx, ry, rz, axes='sxyz'))
    result.apply_translation([float(translation[0]), float(translation[1]), 0.0])
    return result


def generate_top_thumbnail(glb_url: str, scene_name: str, rotation: list[float], translation: list[float], scale: list[float]) -> tuple[str, float]:
    try:
        from PIL import Image, ImageDraw
        import numpy as np
    except Exception as exc:
        raise HTTPException(503, {'map': ['Thumbnail dependencies are unavailable.']}) from exc
    path = media_path(glb_url)
    if path is None or not path.is_file():
        raise HTTPException(400, {'map': ['GLB map file is unavailable.']})
    mesh = _mesh_transform(_load_mesh(path), rotation, translation, scale)
    vertices = np.asarray(mesh.vertices, dtype=float)
    faces = np.asarray(mesh.faces, dtype=int)
    if vertices.size == 0 or faces.size == 0:
        raise HTTPException(400, {'map': ['GLB map has no renderable geometry.']})

    extents = np.asarray(mesh.extents, dtype=float)
    width = max(float(extents[0]), 1e-9)
    height = max(float(extents[1]), 1e-9)
    aspect = THUMBNAIL_WIDTH / THUMBNAIL_HEIGHT
    if width / height > aspect:
        right = width
        top = width / aspect
    else:
        right = height * aspect
        top = height
    pixels_per_meter = THUMBNAIL_HEIGHT / top

    xy = vertices[:, :2]
    mn = xy.min(axis=0)
    # Match the tagged orthographic framing while remaining robust if a custom
    # mesh transform places geometry outside the first quadrant.
    offset_x = (right - width) / 2.0
    offset_y = (top - height) / 2.0
    px = (xy[:, 0] - mn[0] + offset_x) * pixels_per_meter
    py = THUMBNAIL_HEIGHT - (xy[:, 1] - mn[1] + offset_y) * pixels_per_meter

    image = Image.new('RGB', (THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT), (248, 249, 250))
    draw = ImageDraw.Draw(image)
    # Painter's algorithm by mean Z gives a useful deterministic top view
    # without requiring OpenGL/EGL in the control API container.
    ordered = sorted(faces, key=lambda face: float(vertices[face, 2].mean()))
    for face in ordered:
        points = [(float(px[i]), float(py[i])) for i in face]
        draw.polygon(points, fill=(180, 185, 192), outline=(120, 125, 132))
    from io import BytesIO
    buf = BytesIO(); image.save(buf, format='PNG')
    url = store_bytes(f'{scene_name}_2d.png', buf.getvalue(), kind='thumbnail')
    return url, float(pixels_per_meter)


def process_uploaded_mesh(map_url: str, scene_name: str, *, current_rotation=None, current_translation=None, current_scale=None, auto_align: bool = True) -> dict:
    suffix = Path(str(map_url)).suffix.lower()
    value = map_url
    if suffix == '.ply':
        value = convert_point_cloud_ply(map_url, scene_name)
        suffix = '.glb'
    if suffix != '.glb':
        return {'map': value}

    if auto_align:
        rotation, translation = auto_align_glb(value)
    else:
        rotation = list(current_rotation or [0.0, 0.0, 0.0])
        translation = list(current_translation or [0.0, 0.0, 0.0])
    scale = list(current_scale or [1.0, 1.0, 1.0])
    thumbnail, pixels_per_meter = generate_top_thumbnail(value, scene_name, rotation, translation, scale)
    return {
        'map': value,
        'mesh_rotation': rotation,
        'mesh_translation': translation,
        'mesh_scale': scale,
        'thumbnail': thumbnail,
        'scale': pixels_per_meter,
    }
