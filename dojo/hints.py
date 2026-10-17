"""Validated, human-written hint ladders for the judge challenges."""

from __future__ import annotations

import re
from typing import Iterable

_CODE_FENCE = re.compile(r"```|~~~")
_ASSIGNMENT = re.compile(r"(?<![=!<>])=(?!=)")
_CODE_WORDS = re.compile(r"\b(def|return|class|import)\b")
_CALL_WORDS = re.compile(r"\b(range|max|min)\s*\(")

HINTS: dict[str, dict[str, list[str]]] = {
    "last-k-total": {
        "off_by_one": [
            "Compare the number of marks selected with the number requested.",
            "Trace the first and last selected positions for a small list.",
            "Check whether the selection starts one place too early or too late.",
            "Verify the start position at zero, one, and the full-list boundary.",
        ],
        "unhandled_short_input": [
            "Consider what should happen when there are no marks.",
            "Check the case where the requested amount exceeds what is available.",
            "Decide how the available amount should limit the selection.",
            "Trace empty, short, and oversized requests before tracing the ordinary case.",
        ],
        "print_not_return": [
            "The caller needs a value, not only something displayed on screen.",
            "Check what the function gives back after it displays its result.",
            "Follow the value from the calculation to the caller.",
            "Make sure the calculated total is delivered as the function result.",
        ],
        "boundary_comparison": [
            "Look closely at the case where the requested amount meets the list size.",
            "Compare equal-size and just-larger requests.",
            "Check which side of the boundary your selection rule uses.",
            "Trace the exact-size boundary without changing the ordinary case.",
        ],
        "mutates_input": [
            "Check whether the original marks are changed while finding the total.",
            "The caller may need the same list after the calculation.",
            "Trace every operation that changes the collection.",
            "Prefer reasoning that reads the input without altering its order or contents.",
        ],
    },
    "count-passes": {
        "off_by_one": [
            "Count the qualifying marks by hand for a short mixed list.",
            "Compare the number visited with the number counted.",
            "Check whether one mark is being skipped or counted twice.",
            "Trace the first, middle, and last positions on a list with mixed results.",
        ],
        "unhandled_short_input": [
            "A list may contain no marks at all.",
            "Start by deciding what count an empty collection should have.",
            "Check the first access before considering a longer list.",
            "Trace empty, one-item, and two-item inputs separately.",
        ],
        "print_not_return": [
            "Displaying a count is different from giving the count to the caller.",
            "Check the value received by the code that calls the function.",
            "Follow the count after the final qualifying mark is processed.",
            "Ensure the completed count is delivered as the function result.",
        ],
        "boundary_comparison": [
            "Read the threshold wording carefully.",
            "Compare a mark just below the threshold with one exactly at it.",
            "The exact threshold belongs to one side of the comparison.",
            "Trace the exact-threshold case and one neighboring case by hand.",
        ],
        "mutates_input": [
            "Counting should not need to change the marks.",
            "Check whether sorting, removing, or replacing items occurs.",
            "Compare the collection before and after the count.",
            "Keep the input collection available to the caller unchanged.",
        ],
    },
    "first-n-squares": {
        "off_by_one": [
            "Count how many square values the result should contain.",
            "Write the first and last requested positions on paper.",
            "Check whether the sequence starts at the first positive square.",
            "Trace the endpoints for zero, one, and several requested values.",
        ],
        "unhandled_short_input": [
            "Zero is a valid request and has an empty result.",
            "Check what happens before any square values are produced.",
            "The no-items case should finish without needing a position.",
            "Trace zero and one before tracing a larger request.",
        ],
        "print_not_return": [
            "Showing the squares does not give a list back to the caller.",
            "Check what value the caller receives after the display step.",
            "Follow the growing collection to the end of the calculation.",
            "Make the completed collection the function result.",
        ],
        "boundary_comparison": [
            "Check the exact requested count against the number produced.",
            "Compare a request of zero, one, and two.",
            "Look at whether the final requested square is included.",
            "Trace the stopping boundary and count the produced values.",
        ],
        "mutates_input": [
            "The numeric request should not be changed while building the result.",
            "Check every operation that rebinds or alters the input object.",
            "The calculation can use a separate result collection.",
            "Verify the original request remains the same after the call.",
        ],
    },
    "middle-three": {
        "off_by_one": [
            "Find the center position before choosing its neighbors.",
            "The result has three consecutive positions when the list is long enough.",
            "Check whether the chosen group is centered or shifted.",
            "Trace lists of lengths three, five, and seven by hand.",
        ],
        "unhandled_short_input": [
            "The rule changes when fewer than three items exist.",
            "Check the length before assuming there are neighbors on both sides.",
            "Short inputs should remain complete rather than being indexed around.",
            "Trace empty, one-item, two-item, and three-item lists separately.",
        ],
        "print_not_return": [
            "Showing the selected items is not the same as giving back a list.",
            "Check the value received by the caller.",
            "Follow the selected group after it is found.",
            "Deliver the selected list as the function result.",
        ],
        "boundary_comparison": [
            "Focus on the exact length where the rule changes.",
            "Compare two items, three items, and four items.",
            "Check which side of the length boundary uses the whole input.",
            "Trace the boundary case before tracing a longer odd-sized list.",
        ],
        "mutates_input": [
            "Selecting the center should not rearrange or delete the input.",
            "Check whether the original collection changes during selection.",
            "Compare the input before and after the call.",
            "Use a separate result while leaving the caller's collection intact.",
        ],
    },
}


def is_code_like(text: str, function_name: str | None = None) -> bool:
    """Reject obvious code while allowing ordinary instructional prose."""
    if _CODE_FENCE.search(text) or _CODE_WORDS.search(text):
        return True
    if _CALL_WORDS.search(text) or _ASSIGNMENT.search(text):
        return True
    if function_name and re.search(rf"\b{re.escape(function_name)}\b", text):
        return True
    return False


def validate_hints() -> None:
    for challenge_id, ladders in HINTS.items():
        for category, ladder in ladders.items():
            if len(ladder) != 4:
                raise ValueError(f"{challenge_id}/{category} must have four hints")
            if any(is_code_like(hint) for hint in ladder):
                raise ValueError(f"code-like hint in {challenge_id}/{category}")


GENERIC_LADDERS: dict[str, list[str]] = {
    "unhandled_short_input": [
        "Your visible examples all have plenty of items. What should your function return when the input is empty or very short?",
        "Pick the smallest input this problem allows and work it out by hand, line by line. What does each line of your function do with it?",
        "Some operations fail or give the wrong answer when there is nothing, or too little, to work with. Find the first line that depends on the input having enough items.",
        "Handle the too-short case on its own, before the main logic runs, and decide what the problem says it should give back there.",
    ],
    "off_by_one": [
        "Your code gets close but is off by a little. Think about where your loop or slice starts and where it stops.",
        "Take a tiny example with three items and write down which positions your code visits. Compare that to which positions you actually need.",
        "Check whether each end of your range is included or left out. Counting from zero and the end of a range behave differently.",
        "Move one boundary by exactly one step and re-run. Then check the smallest and largest inputs to confirm it holds at both ends.",
    ],
    "print_not_return": [
        "Your function shows a result on screen, but the tests need something different. What does the function hand back to the caller?",
        "Showing a value and handing it back are not the same thing. The tests read what your function gives back, not what appears on screen.",
        "Look at the end of your function. Is there a statement that sends the final answer back to whoever called it?",
        "Make sure every path through your function ends by handing back the final value instead of displaying it.",
    ],
    "boundary_comparison": [
        "Your function works for most values but fails right at a limit. Which value in the problem sits exactly on the edge?",
        "Try the edge value from the problem statement by hand. Does it end up on the side the problem says it should?",
        "Compare how you check the limit with what the problem says. Does the rule include the limit value itself, or only values past it?",
        "Adjust the comparison so the limit value lands on the correct side, then re-test just below, on, and just above the limit.",
    ],
    "mutates_input": [
        "After your function runs, is the list you passed in still the same as before? The problem expects the original to stay untouched.",
        "Some list operations change the list in place, while others build a new one. Which kind is your code using?",
        "Find the line that changes the original list, and work out how to do the same job without altering what was passed in.",
        "Work on a separate copy of the data and give that copy back. Then check the original is unchanged after the call.",
    ],
    "general": [
        "Your code runs, but it does not match what the tests expect. Re-read the problem statement and compare it with what your function actually does.",
        "Pick one visible example and work through your function by hand, line by line. Where does your result first differ from the expected one?",
        "Write down the value of each variable after every step for that example. Look for the first step where a value is not what you expect.",
        "Once you spot the first wrong step, think about the smallest change to that line, then re-run the tests, including very small inputs.",
    ],
}


def get_ladder(challenge_id: str, category: str) -> list[str] | None:
    ladder = HINTS.get(challenge_id, {}).get(category)
    if not ladder:
        ladder = GENERIC_LADDERS.get(category) or GENERIC_LADDERS["general"]
    return list(ladder)


validate_hints()
