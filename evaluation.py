import json
import re


def extract_number(text):
    if not text:
        return None

    matches = re.findall(r"-?\d+\.?\d*", str(text))

    if not matches:
        return None

    return float(matches[0])


def evaluate_numeric_answer(actual_answer, expected_value, tolerance=0.5):
    actual_value = extract_number(actual_answer)

    if actual_value is None:
        return {
            "passed": False,
            "actual_value": None,
            "expected_value": expected_value,
            "error": "No numeric value found in answer"
        }

    difference = abs(actual_value - expected_value)

    return {
        "passed": difference <= tolerance,
        "actual_value": actual_value,
        "expected_value": expected_value,
        "absolute_error": round(difference, 2),
        "tolerance": tolerance
    }


def evaluate_against_ground_truth(answer, metric_name, ground_truth_path="ground_truth.json"):
    with open(ground_truth_path, "r") as file:
        ground_truth = json.load(file)

    if metric_name not in ground_truth:
        return {
            "passed": False,
            "error": f"No ground truth found for metric: {metric_name}"
        }

    expected = ground_truth[metric_name]["expected_value"]
    tolerance = ground_truth[metric_name].get("tolerance", 0.5)

    result = evaluate_numeric_answer(answer, expected, tolerance)
    result["metric_name"] = metric_name
    result["description"] = ground_truth[metric_name].get("description")

    return result