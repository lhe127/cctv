import pytest

from sentinel.analysis import CameraAnalyzer
from sentinel.byte_tracking import ByteTrackAdapter
from sentinel.domain import Camera, Detection, Kind, Rule, Zone
from sentinel.service import MonitorService

POLYGON = ((.1, .1), (.9, .1), (.9, .9), (.1, .9))


def detection(kind=Kind.PERSON, x=.3, confidence=.9):
    return Detection(kind, (x, .3, x+.1, .6), confidence)


def analyzer(rule, **kwargs):
    return CameraAnalyzer(Camera("test", "Test", "synthetic", (Zone("zone", rule, POLYGON, **kwargs),)))


def test_pool_requires_person_and_dwell_and_resets_after_missing_observation():
    a = analyzer(Rule.POOL_SAFETY, dwell_seconds=1)
    assert not a.analyze([detection(Kind.VEHICLE)], 0)[1]
    assert not a.analyze([detection()], .5)[1]
    a.analyze([], 1)
    assert not a.analyze([detection()], 1.5)[1]
    a.analyze([detection()], 2)
    assert a.analyze([detection()], 2.5)[1][0].rule == Rule.POOL_SAFETY


def test_immediate_pool_entry_and_no_alert_outside():
    a = analyzer(Rule.POOL_SAFETY, dwell_seconds=0)
    assert not a.analyze([detection(x=.9)], 0)[1]
    assert len(a.analyze([detection()], .5)[1]) == 1


def test_crowd_is_one_zone_alert_not_one_alert_per_person():
    a = analyzer(Rule.CROWD, dwell_seconds=1, min_count=2, cooldown_seconds=5)
    people = [detection(x=.2), detection(x=.5)]
    assert not a.analyze(people, 0)[1]
    assert not a.analyze([people[0], detection(Kind.VEHICLE, x=.5)], .5)[1]
    assert not a.analyze(people, 1)[1]
    a.analyze(people, 1.5)
    events = a.analyze(people, 2)[1]
    assert len(events) == 1 and events[0].track_id is None
    assert '2 people' in events[0].message
    assert not a.analyze(people, 2.5)[1]
    assert not a.analyze(people, 7)[1]  # No continuous dwell over a telemetry gap.


def test_parking_requires_stationary_vehicle_and_resets_slow_creeping():
    a = analyzer(Rule.ILLEGAL_PARKING, dwell_seconds=2, stationary_tolerance=.025)
    for at in (0, .5, 1, 1.5, 2):
        assert not a.analyze([detection()], at)[1]
    for i in range(8):
        assert not a.analyze([detection(Kind.VEHICLE, x=.3+i*.015)], 3+i*.5)[1]
    parked = detection(Kind.VEHICLE, x=.405)
    events = []
    for at in (7, 7.5, 8, 8.5, 9):
        events.extend(a.analyze([parked], at)[1])
    assert len(events) == 1 and events[0].rule == Rule.ILLEGAL_PARKING


def test_invalid_new_thresholds():
    for kwargs in ({"min_count": 1}, {"min_count": 2.5}, {"stationary_tolerance": 0},
                   {"stationary_tolerance": float('nan')}, {"dwell_seconds": float('inf')}):
        with pytest.raises(ValueError):
            Zone("bad", Rule.CROWD, POLYGON, **kwargs)


def test_unattended_bag_proximity_and_motion_reset():
    a = analyzer(Rule.UNATTENDED_OBJECT, dwell_seconds=1, proximity_radius=.15)
    bag = detection(Kind.OBJECT, x=.3)
    assert not a.analyze([bag, detection(x=.35)], 0)[1]
    assert not a.analyze([bag, detection(x=.35)], .5)[1]
    assert not a.analyze([bag, detection(x=.7)], 1)[1]
    a.analyze([bag], 1.5)
    events = a.analyze([bag], 2)[1]
    assert len(events) == 1 and events[0].rule == Rule.UNATTENDED_OBJECT
    b = analyzer(Rule.UNATTENDED_OBJECT, dwell_seconds=1)
    for i in range(5):
        assert not b.analyze([detection(Kind.OBJECT, x=.2+.04*i)], i*.5)[1]


def test_bytetrack_retains_id_on_low_confidence_and_brief_occlusion():
    tracker = ByteTrackAdapter()
    first = tracker.update([detection()], 0)[0].id
    assert tracker.update([detection(confidence=.2)], .5)[0].id == first
    assert tracker.update([], 1) == []
    assert tracker.update([detection()], 1.5)[0].id == first
    assert tracker.update([detection()], 5)[0].id != first


def test_bytetrack_class_camera_isolation_and_new_low_confidence_suppression():
    a, b = ByteTrackAdapter(), ByteTrackAdapter()
    assert a.update([detection(confidence=.2)], 0) == []
    a = ByteTrackAdapter()
    tracks = a.update([detection(), detection(Kind.VEHICLE)], 0)
    assert len(tracks) == 2 and tracks[0].id != tracks[1].id
    assert b.update([detection()], 0)[0].id == 1


def test_shared_service_and_direct_analyzer_produce_same_events():
    zones = tuple(Zone(rule.value, rule, POLYGON, dwell_seconds=1, min_count=2)
                  for rule in (Rule.INTRUSION, Rule.POOL_SAFETY, Rule.CROWD, Rule.ILLEGAL_PARKING))
    camera = Camera("test", "Test", "synthetic", zones)
    service = MonitorService(tracker_factory=ByteTrackAdapter)
    service.add_camera(camera)
    direct = CameraAnalyzer(camera, ByteTrackAdapter())
    for at in (0, .5, 1, 1.5, 2):
        detections = [detection(x=.2), detection(x=.5), detection(Kind.VEHICLE, x=.7)]
        live_events = service.observe("test", detections, at)[1]
        test_events = direct.analyze(detections, at)[1]
        assert [(e.rule, e.zone_id, e.track_id, e.observed_at) for e in live_events] == [
            (e.rule, e.zone_id, e.track_id, e.observed_at) for e in test_events]
