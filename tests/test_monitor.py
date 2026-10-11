import unittest

from sentinel.domain import Camera, Detection, Kind, Rule, Zone
from sentinel.service import MonitorService


def rectangle(name, rule, x1=0.1, y1=0.1, x2=0.9, y2=0.9, dwell=2):
    return Zone(name, rule, ((x1, y1), (x2, y1), (x2, y2), (x1, y2)), dwell_seconds=dwell)


def person(y1=0.3, y2=0.6, x1=0.3, x2=0.4, activity=0):
    return Detection(Kind.PERSON, (x1, y1, x2, y2), 0.9, activity)


class MonitorTests(unittest.TestCase):
    def test_intrusion_and_camera_isolation(self):
        service = MonitorService()
        service.add_camera(Camera("a", "A", "synthetic", (rectangle("restricted", Rule.INTRUSION),)))
        service.add_camera(Camera("b", "B", "synthetic", ()))
        tracks, events = service.observe("a", [person()], 100)
        self.assertEqual(len(events), 1)
        self.assertEqual(tracks[0].id, 1)
        self.assertEqual(service.tracks("b"), [])
        self.assertEqual(service.observe("a", [person()], 101)[1], [])
        self.assertEqual(len(service.events("a")), 1)
        self.assertEqual(len(service.events("b")), 0)

    def test_loitering_and_exit_reset(self):
        service = MonitorService()
        service.add_camera(Camera("a", "A", "synthetic", (rectangle("wait", Rule.LOITERING),)))
        self.assertEqual(service.observe("a", [person()], 100)[1], [])
        self.assertEqual(service.observe("a", [person()], 101)[1], [])
        self.assertEqual(len(service.observe("a", [person()], 102)[1]), 1)
        self.assertEqual(service.observe("a", [person(x1=0.92, x2=0.99)], 103)[1], [])

    def test_wall_climb_and_tamper_are_conditional(self):
        service = MonitorService()
        service.add_camera(Camera("a", "A", "synthetic", (rectangle("wall", Rule.WALL_CLIMBING, dwell=1),
            rectangle("door", Rule.DOOR_TAMPERING, dwell=1))))
        service.observe("a", [person(activity=0.1)], 100)
        self.assertEqual(service.observe("a", [person(y1=0.24, y2=0.54, activity=0.8)], 101)[1], [])
        _, events = service.observe("a", [person(y1=0.17, y2=0.47, activity=0.8)], 102)
        self.assertEqual({event.rule for event in events}, {Rule.WALL_CLIMBING, Rule.DOOR_TAMPERING})

    def test_one_frame_motion_does_not_trigger_behavior_alert(self):
        service = MonitorService()
        service.add_camera(Camera("a", "A", "synthetic", (rectangle("wall", Rule.WALL_CLIMBING, dwell=1),
            rectangle("door", Rule.DOOR_TAMPERING, dwell=1))))
        service.observe("a", [person()], 100)
        self.assertEqual(service.observe("a", [person(y1=0.16, y2=0.46, activity=1)], 101)[1], [])
        self.assertEqual(service.observe("a", [person(y1=0.3, y2=0.6)], 102)[1], [])

    def test_wall_crossing_line_is_required_when_configured(self):
        zone = Zone("wall", Rule.WALL_CLIMBING,
                    ((0.1, 0.1), (0.9, 0.1), (0.9, 0.9), (0.1, 0.9)),
                    dwell_seconds=1, min_vertical_travel=0.12, crossing_line_y=0.5)
        service = MonitorService()
        service.add_camera(Camera("a", "A", "synthetic", (zone,)))
        service.observe("a", [person(y1=0.5, y2=0.8)], 100)
        service.observe("a", [person(y1=0.44, y2=0.74)], 101)
        self.assertEqual(service.observe("a", [person(y1=0.38, y2=0.68)], 102)[1], [])
        service.observe("a", [person(y1=0.27, y2=0.57)], 103)
        _, events = service.observe("a", [person(y1=0.19, y2=0.49)], 104)
        self.assertEqual([event.rule for event in events], [Rule.WALL_CLIMBING])

    def test_door_zone_motion_can_alert_without_person_detection(self):
        zone = rectangle("handle", Rule.DOOR_TAMPERING, dwell=1)
        service = MonitorService()
        service.add_camera(Camera("a", "A", "synthetic", (zone,)))
        self.assertEqual(service.observe("a", [], 100, {"handle": 0.9})[1], [])
        _, events = service.observe("a", [], 101, {"handle": 0.9})
        self.assertEqual(len(events), 1)
        self.assertIsNone(events[0].track_id)
        self.assertIsNone(events[0].kind)
        self.assertEqual(service.observe("a", [], 102, {"handle": 0.0})[1], [])

    def test_vehicle_tracking_and_bad_geometry(self):
        service = MonitorService()
        service.add_camera(Camera("a", "A", "synthetic", (rectangle("restricted", Rule.INTRUSION),)))
        vehicle = Detection(Kind.VEHICLE, (0.2, 0.2, 0.4, 0.5), 0.8)
        first = service.observe("a", [vehicle], 100)[0][0]
        second = service.observe("a", [vehicle], 101)[0][0]
        self.assertEqual(first.id, second.id)
        self.assertEqual(service.events(), [])
        self.assertEqual(len(service.detections()), 1)
        service.observe("a", [], 101.5)
        service.observe("a", [vehicle], 102)
        self.assertEqual(len(service.detections()), 1)
        with self.assertRaises(ValueError):
            Detection(Kind.PERSON, (0.9, 0.1, 0.2, 0.6), 0.9)

    def test_missing_camera_and_bounded_events(self):
        service = MonitorService(max_events=1)
        service.add_camera(Camera("a", "A", "synthetic", (rectangle("restricted", Rule.INTRUSION),)))
        service.observe("a", [person()], 100)
        service.observe("a", [person(x1=0.6, x2=0.7)], 101)
        self.assertEqual(len(service.events()), 1)
        with self.assertRaises(KeyError):
            service.tracks("missing")

    def test_bad_timestamp_rejected(self):
        service = MonitorService()
        service.add_camera(Camera("a", "A", "synthetic"))
        with self.assertRaises(ValueError):
            service.observe("a", [person()], float("nan"))
        service.observe("a", [person()], 100)
        with self.assertRaises(ValueError):
            service.observe("a", [person()], 99)


if __name__ == "__main__":
    unittest.main()
