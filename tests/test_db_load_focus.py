"""Tests for training load balance ("Load Focus") ingestion into load_focus."""

from garmin_mcp.db import save_to_db


def _payload(devices):
    return {"metricsTrainingLoadBalanceDTOMap": devices, "recordedDevices": [], "userId": 1}


def _dto(device_id, calendar_date, primary=True, high=1136.7, low=982.9, anaerobic=360.8, phrase="ON_TARGET"):
    return {
        "calendarDate": calendar_date,
        "deviceId": device_id,
        "monthlyLoadAerobicHigh": high,
        "monthlyLoadAerobicHighTargetMax": 1820,
        "monthlyLoadAerobicHighTargetMin": 1122,
        "monthlyLoadAerobicLow": low,
        "monthlyLoadAerobicLowTargetMax": 1666,
        "monthlyLoadAerobicLowTargetMin": 968,
        "monthlyLoadAnaerobic": anaerobic,
        "monthlyLoadAnaerobicTargetMax": 561,
        "monthlyLoadAnaerobicTargetMin": 142,
        "primaryTrainingDevice": primary,
        "trainingBalanceFeedbackPhrase": phrase,
    }


def _rows(conn):
    return [
        tuple(r)
        for r in conn.execute(
            "SELECT calendar_date, anaerobic, high_aerobic, low_aerobic, focus_status FROM load_focus"
        ).fetchall()
    ]


class TestLoadFocus:
    def test_stores_monthly_loads_and_status(self, temp_db):
        n = save_to_db(temp_db, "training_load_balance", _payload({"111": _dto(111, "2026-10-09")}), "2026-10-09")
        assert n == 1
        assert _rows(temp_db) == [("2026-10-09", 360.8, 1136.7, 982.9, "ON_TARGET")]

    def test_prefers_primary_training_device(self, temp_db):
        devices = {
            "1": _dto(1, "2026-10-09", primary=False, phrase="AEROBIC_LOW_SHORTAGE"),
            "2": _dto(2, "2026-10-09", primary=True, phrase="ON_TARGET"),
        }
        save_to_db(temp_db, "training_load_balance", _payload(devices), "2026-10-09")
        assert _rows(temp_db)[0][4] == "ON_TARGET"

    def test_uses_dto_date_not_requested_date(self, temp_db):
        # 'latest/{date}' returns the most recent balance as of that date.
        save_to_db(temp_db, "training_load_balance", _payload({"1": _dto(1, "2026-10-06")}), "2026-10-09")
        assert _rows(temp_db)[0][0] == "2026-10-06"

    def test_empty_payload_is_skipped(self, temp_db):
        assert save_to_db(temp_db, "training_load_balance", _payload({}), "2026-10-09") == 0
        assert save_to_db(temp_db, "training_load_balance", {"data": None, "status": 204}, "2026-10-09") == 0
        assert _rows(temp_db) == []
