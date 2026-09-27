# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from datetime import datetime, timedelta, timezone

from scenescape_api.bluetooth_fusion import EntityFusionProvider, FusionConfig


BASE = datetime(2026, 9, 26, 10, 0, tzinfo=timezone.utc)


def _vision(object_id, x, y, *, category="person", t=0):
  return {
      "id": object_id,
      "category": category,
      "translation": [x, y, 1.0],
      "velocity": [0.1, 0.0, 0.0],
      "timestamp": (BASE + timedelta(seconds=t)).isoformat(),
  }


def _bt(
    tag_id,
    x,
    y,
    *,
    entity_type="person",
    entity_id="worker-7",
    display_name=None,
    identity_revision="assign-1",
    score=0.95,
    t=0,
):
  return {
      "id": f"bt:{tag_id}",
      "source": "bluetooth",
      "category": entity_type,
      "translation": [x, y, 1.0],
      "timestamp": (BASE + timedelta(seconds=t)).isoformat(),
      "bluetooth": {
          "tag_id": tag_id,
          "score": score,
          "identity_revision": identity_revision,
          "assignment": {
              "entity_type": entity_type,
              "entity_id": entity_id,
              "display_name": display_name,
          },
      },
  }


def test_bt15_strong_one_to_one_association_fuses_and_retains_sources():
  provider = EntityFusionProvider()
  vision = _vision("vision-1", 5.0, 5.0)
  bt = _bt("tag-a", 5.1, 5.0, display_name="Worker 7")

  result = provider.fuse([vision], [bt])

  assert len(result["fused"]) == 1
  fused = result["fused"][0]
  assert fused["id"] == "fused:tag-a"
  assert fused["label"] == "Worker 7"
  assert fused["fusion"]["identity_source"] == "explicit_bluetooth_assignment"
  assert fused["fusion"]["source_ids"] == {
      "bluetooth": "bt:tag-a",
      "vision": "vision-1",
  }
  assert fused["source_objects"]["vision"] == vision
  assert fused["source_objects"]["bluetooth"] == bt
  assert result["objects"] == [fused]


def test_bt15_visual_appearance_never_creates_named_identity():
  provider = EntityFusionProvider()
  vision = {
      **_vision("vision-famous-face", 2.0, 2.0),
      "name": "Alice",
      "face_identity": "Alice",
  }
  bt = _bt(
      "tag-a",
      2.05,
      2.0,
      entity_id="anonymous-asset-ref",
      display_name=None,
  )

  fused = provider.fuse([vision], [bt])["fused"][0]
  assert fused["label"] == "anonymous-asset-ref"
  assert fused["label"] != "Alice"
  assert fused["fusion"]["identity_source"] == "explicit_bluetooth_assignment"


def test_bt15_category_mismatch_stays_separate():
  provider = EntityFusionProvider()
  result = provider.fuse(
      [_vision("person-1", 4.0, 4.0, category="person")],
      [_bt("forklift-tag", 4.0, 4.0, entity_type="asset", entity_id="forklift-1")],
  )

  assert result["fused"] == []
  assert len(result["unmatched_vision"]) == 1
  assert len(result["unmatched_bluetooth"]) == 1
  assert provider.metrics["category_rejected"] > 0


def test_bt15_crossing_tracks_are_not_forced_when_ambiguous():
  provider = EntityFusionProvider(
      FusionConfig(
          max_distance_m=2.0,
          minimum_confidence=0.60,
          ambiguity_margin=0.20,
          retain_confidence=0.50,
      )
  )
  vision = [
      _vision("v1", 5.0, 5.0),
      _vision("v2", 5.15, 5.0),
  ]
  bt = _bt("tag-a", 5.075, 5.0)

  result = provider.fuse(vision, [bt])

  assert result["fused"] == []
  assert provider.metrics["ambiguous"] == 1
  assert len(result["objects"]) == 3


def test_bt15_hysteresis_retains_stable_association_through_small_motion():
  provider = EntityFusionProvider(
      FusionConfig(
          max_distance_m=1.5,
          minimum_confidence=0.70,
          ambiguity_margin=0.05,
          retain_confidence=0.55,
      )
  )
  first = provider.fuse(
      [_vision("v1", 1.0, 1.0, t=0)],
      [_bt("tag-a", 1.05, 1.0, t=0)],
  )
  assert first["fused"][0]["fusion"]["vision_object_id"] == "v1"

  second = provider.fuse(
      [
          _vision("v1", 1.7, 1.0, t=0.5),
          _vision("v2", 2.3, 1.0, t=0.5),
      ],
      [_bt("tag-a", 1.65, 1.0, t=0.5)],
  )
  assert second["fused"][0]["fusion"]["vision_object_id"] == "v1"


def test_bt15_identity_revision_change_splits_previous_association():
  provider = EntityFusionProvider()
  first = provider.fuse(
      [_vision("v1", 1.0, 1.0)],
      [_bt("tag-a", 1.0, 1.0, identity_revision="assign-1")],
  )
  assert first["fused"]

  second = provider.fuse(
      [_vision("v1", 1.0, 1.0, t=0.2)],
      [_bt("tag-a", 1.0, 1.0, identity_revision="assign-2", t=0.2)],
  )
  assert second["fused"]
  assert provider.metrics["split"] >= 1
  assert second["fused"][0]["fusion"]["identity_revision"] == "assign-2"


def test_bt15_dropout_keeps_sources_separate_without_hallucinated_bridge():
  provider = EntityFusionProvider()
  provider.fuse(
      [_vision("v1", 1.0, 1.0)],
      [_bt("tag-a", 1.0, 1.0)],
  )
  result = provider.fuse([], [_bt("tag-a", 1.2, 1.0, t=1)])

  assert result["fused"] == []
  assert result["unmatched_bluetooth"][0]["id"] == "bt:tag-a"
  assert provider.metrics["split"] >= 1


def test_bt15_bad_fix_outside_gate_never_overrides_vision():
  provider = EntityFusionProvider(FusionConfig(max_distance_m=1.0))
  vision = _vision("v1", 0.0, 0.0)
  bt = _bt("tag-a", 20.0, 20.0)

  result = provider.fuse([vision], [bt])

  assert result["fused"] == []
  assert result["objects"][0] == vision
  assert result["objects"][1] == bt
