# Use the Scenescape User Interface

The Scenescape user interface provides a scene-oriented workspace for monitoring live activity, investigating retained data, and configuring scene resources.

## Time to complete

5-15 minutes

## Prerequisites

- Complete the [Installation](../get-started/installation.md) procedure.
- Use an account with access to the scenes you need to view.
- Administrator privileges are required for configuration changes.

## Open the user interface

Open the Scenescape UI URL configured by your deployment and sign in through Keycloak.

For local or evaluation deployments, the exposed URL depends on the compose or Kubernetes configuration. If the deployment uses a self-signed certificate, the browser can display a certificate warning until the deployment is configured with a trusted certificate.

## Open a scene

From the scene inventory or overview, select **Open live view** for a scene.

The Scene Workspace keeps the scene's operational state visible while you move between views.

The status header shows the available values for:

- Overall scene state: **LIVE**, **DEGRADED**, or **STALE/OFFLINE**.
- Current tracked-object count.
- Scene update rate.
- Camera health summary.
- MQTT ingestion state.
- Age of the latest retained observation.

If a value is unavailable, the UI displays **Unknown** instead of treating missing data as a healthy or zero value.

## Use Monitor mode

**Monitor** is the default Scene Workspace mode.

The available views are:

- **2D Scene**: View the scene map, tracked objects, regions, tripwires, cameras, and sensors.
- **3D Scene**: View the scene in the native Three.js renderer.
- **Cameras**: View configured camera feeds and optional camera telemetry.
- **Sensors**: View retained sensor telemetry.

### Control scene layers

The **Layers** group controls what is drawn in the active scene renderer.

Common controls include:

- Objects.
- Trails.
- Heatmap.
- Velocity.
- Spatial overlays.

The 2D view also provides a **Labels** control.

The 3D view provides renderer-specific controls such as the floor plane, projected camera frames, camera selection, camera view, camera opacity, and scene lighting.

Controls that do not apply to the active renderer are not displayed.

### Use diagnostics

Enable **Telemetry** in the **Diagnostics** group to display the scene telemetry HUD.

The HUD can show:

- Scene update rate.
- Object count.
- Latest observation age.
- Per-camera FPS when it is present in the live scene feed.
- Feed freshness.

Missing rates remain **Unknown** rather than being displayed as zero.

### Inspect an entity

Select a tracked object, camera, sensor, region, or tripwire in the 2D scene to open the contextual inspector.

Tracked objects can also be selected in the 3D view by using the tracked-object selector or by selecting the rendered object.

Depending on the entity and available data, the inspector can show:

- Identity and category.
- Position.
- Velocity and numeric speed.
- Current regions and dwell time.
- Camera visibility.
- Persistent object data.
- Camera FPS, detections, and feed freshness.
- Sensor type and latest retained reading.
- Region or tripwire geometry and configured thresholds.

Unavailable optional fields are displayed as **Unknown**.

### Use heatmap and velocity overlays

The current heatmap visualizes the relative intensity of **current tracked positions**. Use the heatmap opacity control to reduce or increase the overlay strength.

Historical heatmap ranges are not displayed unless the deployment provides an explicit retained-density data contract.

Velocity arrows are drawn only for objects that report a valid velocity vector. The UI shows the number of usable vectors, for example **2/5 vectors**, so a missing upstream velocity value is not mistaken for a rendering failure.

### Use fullscreen

Select **Fullscreen** to expand the active 2D or 3D visualization. Exit browser fullscreen normally to return to the Scene Workspace.

## Use Analyze mode

Select **Analyze** to work with retained operational data.

The views are:

- **History**: Load persisted scene observations and replay available history.
- **Trends**: Query retained trend aggregates for the selected range.
- **Runtime**: Inspect native runtime health such as MQTT ingestion.

The Analyze views remain scoped to the active scene.

## Use Configure mode

Select **Configure** for scene configuration.

The available destinations are:

- **Scene**: Open the scene inventory/configuration surface.
- **Cameras**: Open camera configuration.
- **Sensors**: Open sensor configuration.
- **Geometry**: Configure regions and tripwires for the active scene.
- **Hierarchy**: Configure parent/child scene links.
- **Calibration**: Configure camera calibration for the active scene.

Configuration changes continue to use native revision checks. If another editor changes the same resource first, the stale update is rejected instead of silently overwriting the newer state.

## Keyboard and accessibility behavior

Primary and secondary navigation use native keyboard-operable controls.

In the 2D scene, selectable objects, cameras, sensors, regions, and tripwires can be focused and opened with **Enter** or **Space**.

Visible focus styling identifies the current keyboard target.

Scene state changes use a polite accessibility announcement. Rapidly changing telemetry metrics are not continuously announced, which avoids excessive screen-reader output.

Operational state is always shown as text and is not communicated by color alone.

## Navigate the online documentation

Scenescape documentation is available from the documentation links provided by the deployment.

Use the documentation navigation to open the user guide, API reference, architecture information, hardening guidance, and troubleshooting material.

## Summary

The Scene Workspace separates three operator intents:

1. **Monitor** current scene activity.
2. **Analyze** retained history, trends, and runtime state.
3. **Configure** the scene and its resources.

This structure keeps live operations visible while moving detailed diagnostics and configuration into their appropriate contexts.

## Learn more

- [Build a Scene](./build-a-scene/index.md)
- [Calibrate Cameras](./calibrate-cameras/index.md)
- [Work with Spatial Analytics Data](./work-with-spatial-analytics-data.md)
- [API Reference](../api-reference.md)
