"""
Tests for nutrition capture (garmin-givemydata).

Covers the two tables fed by /gc-api/nutrition-service/food/logs/{date}:
  - nutrition_daily:    one row per day, consumed totals
  - nutrition_food_log: one row per logged food, nutrients scaled by servingQty

Verifies schema presence, extraction/scaling, the save_to_db route, and that
re-syncing the same day updates rows (log_id / date primary keys) rather than
duplicating them.
"""

import json

from garmin_mcp.db import (
    _extract_nutrition_daily,
    _extract_nutrition_food_log,
    save_to_db,
)


def _cols(conn, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


# A trimmed but structurally faithful food/logs payload.
SAMPLE = {
    "mealDate": "2026-05-15",
    "dailyNutritionContent": {
        "calories": 2185,
        "caloriesPercentage": 110,
        "carbs": 229,
        "fat": 86,
        "protein": 138,
    },
    "dailyNutritionGoals": {"calories": 2000},
    "mealDetails": [
        {
            "meal": {"mealName": "BREAKFAST"},
            "loggedFoods": [
                {
                    "logId": "log-aaa",
                    "id": "2920600",
                    "isFavorite": True,
                    "logTimestamp": "2026-05-15T15:30:00.000Z",
                    "mealTime": "11:30:00",
                    "servingQty": 2,
                    "foodMetaData": {
                        "foodId": "2920600",
                        "foodName": "Energy Bar",
                        "brandName": "Clif Bar",
                        "foodType": "BRAND",
                        "source": "FATSECRET",
                    },
                    "nutritionContent": {
                        "calories": 250,
                        "carbs": 43,
                        "fat": 6,
                        "protein": 9,
                        "fiber": 5,
                        "sugar": 20,
                        "sodium": 200,
                        "vitaminD": 10,
                        "numberOfUnits": 1,
                        "servingUnit": "bar",
                    },
                }
            ],
        },
        {
            "meal": {"mealName": "LUNCH"},
            "loggedFoods": [
                {
                    "logId": "log-bbb",
                    "id": "56662",
                    "isFavorite": False,
                    "logTimestamp": "2026-05-15T19:00:00.000Z",
                    "mealTime": "13:30:00",
                    "servingQty": 1.1,
                    "foodMetaData": {
                        "foodId": "56662",
                        "foodName": "Elbow Macaroni",
                        "source": "FATSECRET",
                    },
                    "nutritionContent": {
                        "calories": 357,
                        "carbs": 75,
                        "fat": 1.79,
                        "protein": 12.5,
                        "numberOfUnits": 100,
                        "servingUnit": "g",
                    },
                },
                {
                    # No logId — must be skipped (can't key it).
                    "id": "x",
                    "servingQty": 1,
                    "foodMetaData": {"foodName": "Ghost", "source": "GARMIN"},
                    "nutritionContent": {"calories": 99},
                },
            ],
        },
    ],
}


class TestSchema:
    def test_tables_exist(self, temp_db):
        daily = _cols(temp_db, "nutrition_daily")
        assert {"calendar_date", "calories", "protein", "fat", "carbs", "raw_json"} <= daily

        food = _cols(temp_db, "nutrition_food_log")
        for col in (
            "log_id", "calendar_date", "logged_at", "meal_time", "food_name",
            "brand_name", "food_type", "food_source", "food_id", "serving_qty",
            "serving_unit", "serving_base_units", "is_favorite", "calories",
            "protein", "fat", "carbs", "fiber", "sugar", "added_sugars",
            "saturated_fat", "monounsaturated_fat", "polyunsaturated_fat",
            "trans_fat", "cholesterol", "sodium", "potassium", "calcium",
            "iron", "vitamin_a", "vitamin_c", "vitamin_d", "raw_json",
        ):
            assert col in food, f"Missing column: {col}"


class TestExtraction:
    def test_daily_totals(self):
        recs = _extract_nutrition_daily(SAMPLE, cal_date=None)
        assert len(recs) == 1
        r = recs[0]
        assert r["calendar_date"] == "2026-05-15"
        assert r["calories"] == 2185
        assert r["protein"] == 138
        assert r["fat"] == 86
        assert r["carbs"] == 229

    def test_daily_skipped_when_no_content(self):
        assert _extract_nutrition_daily({"mealDate": "2026-05-15"}, None) == []
        assert _extract_nutrition_daily(
            {"mealDate": "2026-05-15", "dailyNutritionContent": {}}, None
        ) == []

    def test_food_rows_scaled_by_serving_qty(self):
        rows = {r["log_id"]: r for r in _extract_nutrition_food_log(SAMPLE, None)}
        # The no-logId entry is dropped.
        assert set(rows) == {"log-aaa", "log-bbb"}

        bar = rows["log-aaa"]
        assert bar["calendar_date"] == "2026-05-15"
        assert bar["food_name"] == "Energy Bar"
        assert bar["brand_name"] == "Clif Bar"
        assert bar["food_source"] == "FATSECRET"
        assert bar["serving_qty"] == 2
        assert bar["serving_unit"] == "bar"
        assert bar["is_favorite"] == 1
        # Consumed = per-serving * servingQty (2).
        assert bar["calories"] == 500
        assert bar["carbs"] == 86
        assert bar["fiber"] == 10
        assert bar["vitamin_d"] == 20
        # Absent nutrients stay NULL, not 0.
        assert bar["iron"] is None

        pasta = rows["log-bbb"]
        assert pasta["is_favorite"] == 0
        assert pasta["calories"] == round(357 * 1.1, 4)
        assert pasta["protein"] == round(12.5 * 1.1, 4)


class TestSaveToDb:
    def test_route_populates_both_tables(self, temp_db):
        n = save_to_db(temp_db, "nutrition", SAMPLE, cal_date="2026-05-15")
        # 1 daily + 2 food rows.
        assert n == 3

        daily = temp_db.execute(
            "SELECT calories, protein FROM nutrition_daily WHERE calendar_date = ?",
            ("2026-05-15",),
        ).fetchone()
        assert daily["calories"] == 2185
        assert daily["protein"] == 138

        foods = temp_db.execute(
            "SELECT COUNT(*) c FROM nutrition_food_log WHERE calendar_date = ?",
            ("2026-05-15",),
        ).fetchone()
        assert foods["c"] == 2

    def test_resync_updates_not_duplicates(self, temp_db):
        save_to_db(temp_db, "nutrition", SAMPLE, cal_date="2026-05-15")
        save_to_db(temp_db, "nutrition", SAMPLE, cal_date="2026-05-15")

        assert temp_db.execute(
            "SELECT COUNT(*) FROM nutrition_daily"
        ).fetchone()[0] == 1
        assert temp_db.execute(
            "SELECT COUNT(*) FROM nutrition_food_log"
        ).fetchone()[0] == 2

    def test_raw_json_roundtrips(self, temp_db):
        save_to_db(temp_db, "nutrition", SAMPLE, cal_date="2026-05-15")
        raw = temp_db.execute(
            "SELECT raw_json FROM nutrition_food_log WHERE log_id = 'log-aaa'"
        ).fetchone()[0]
        assert json.loads(raw)["foodMetaData"]["foodName"] == "Energy Bar"
