from __future__ import annotations

from typing import Any

from fastapi import HTTPException


def _bad(message: str) -> None:
    raise HTTPException(400, {'error': message})


def _matrix_to_euler_xyz(rotation_matrix):
    # scipy Rotation.as_euler('XYZ') equivalent for a proper rotation matrix.
    import math
    import numpy as np
    m = rotation_matrix
    sy = max(-1.0, min(1.0, float(m[0, 2])))
    y = math.asin(sy)
    cy = math.cos(y)
    if abs(cy) > 1e-8:
        x = math.atan2(-float(m[1, 2]), float(m[2, 2]))
        z = math.atan2(-float(m[0, 1]), float(m[0, 0]))
    else:
        x = math.atan2(float(m[2, 1]), float(m[1, 1]))
        z = 0.0
    return np.array([x, y, z], dtype=np.float64)


def _y_up_to_y_down(rotation_matrix):
    import numpy as np
    # Ry(pi) @ Rz(pi) == diag(1,-1,-1). Avoid a runtime scipy dependency.
    return rotation_matrix @ np.diag([1.0, -1.0, -1.0])


def _calculate_pose(rvec, tvec):
    import cv2
    import numpy as np
    rotation, _ = cv2.Rodrigues(rvec)
    transform = np.array([
        [rotation[0, 0], rotation[0, 1], rotation[0, 2], tvec[0, 0]],
        [-rotation[1, 0], -rotation[1, 1], -rotation[1, 2], -tvec[1, 0]],
        [-rotation[2, 0], -rotation[2, 1], -rotation[2, 2], -tvec[2, 0]],
        [0, 0, 0, 1],
    ])
    inv = np.linalg.inv(transform)
    euler = _matrix_to_euler_xyz(_y_up_to_y_down(inv[:3, :3]))
    position = inv[:3, 3]
    return euler, position


def calculate_camera_intrinsics(data: dict[str, Any]) -> dict[str, Any]:
    try:
        import cv2
        import numpy as np
    except Exception as exc:
        raise HTTPException(503, {'error': 'Camera calibration dependencies are unavailable'}) from exc

    if not isinstance(data, dict):
        _bad('Invalid values provided for calculation')
    required = ['mapPoints', 'camPoints', 'intrinsics', 'distortion', 'imageSize']
    missing = [field for field in required if field not in data]
    if missing:
        _bad(f"Missing required fields: {', '.join(missing)}")
    if len(data['mapPoints']) != len(data['camPoints']) or len(data['mapPoints']) < 4:
        _bad('Invalid number of points provided for calculation.')

    try:
        obj_points = np.array(data['mapPoints'], dtype=np.float32)
        img_points = np.array(data['camPoints'], dtype=np.float32)
        if obj_points.ndim != 2 or obj_points.shape[1] != 3:
            raise ValueError('mapPoints must be Nx3')
        if img_points.ndim != 2 or img_points.shape[1] != 2:
            raise ValueError('camPoints must be Nx2')
        num_points = len(obj_points)
        intrinsics = np.array(data['intrinsics'], dtype=np.float64)
        if intrinsics.shape != (3, 3):
            raise ValueError('intrinsics must be 3x3')
        distortion = np.array(data['distortion'], dtype=np.float64)
        distortion = np.nan_to_num(distortion, nan=0.0)
        image_size = tuple(map(int, data['imageSize']))
        if len(image_size) != 2 or min(image_size) <= 0:
            raise ValueError('imageSize must contain positive width and height')

        flags = cv2.CALIB_USE_INTRINSIC_GUESS | cv2.CALIB_FIX_ASPECT_RATIO
        calibrate_flags = [
            (['fx', 'fy'], cv2.CALIB_FIX_FOCAL_LENGTH, 6),
            (['cx', 'cy'], cv2.CALIB_FIX_PRINCIPAL_POINT, 6),
            (['k1'], cv2.CALIB_FIX_K1, 8),
            (['k2'], cv2.CALIB_FIX_K2, 8),
            (['k3'], cv2.CALIB_FIX_K3, 8),
            (['p1', 'p2'], cv2.CALIB_FIX_TANGENT_DIST, 8),
        ]
        fix_intrinsics = data.get('fixIntrinsics', {}) or {}
        for keys, flag, min_points in calibrate_flags:
            if any(fix_intrinsics.get(key, True) for key in keys) or num_points < min_points:
                flags |= flag

        _, matrix, dist, rvecs, tvecs = cv2.calibrateCamera(
            [obj_points], [img_points], image_size, intrinsics, distortion, flags=flags
        )
        euler, position = _calculate_pose(rvecs[0], tvecs[0])
        return {
            'euler': euler.tolist(),
            'position': position.tolist(),
            'mtx': matrix.tolist(),
            'dist': dist.tolist(),
        }
    except HTTPException:
        raise
    except (cv2.error, TypeError, ValueError, KeyError, IndexError) as exc:
        raise HTTPException(400, {'error': 'Invalid values provided for calculation'}) from exc
