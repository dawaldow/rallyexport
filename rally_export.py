import calendar
import csv
import getpass
import html
import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# ============================================================
# VARIABLES YOU NEED TO SUPPLY
# ============================================================
WORKSPACE = "35536700027"
PROJECT = "<project id goes here>"
TEAM_NAME = "<team name goes here>"  # no spaces, no special characters, just letters and numbers
API_KEY = "<api key goes here>"

# ============================================================
# CONFIGURATION
# ============================================================
RALLY_BASE_URL = "https://rally1.rallydev.com/slm/webservice/v2.0"
INCLUDE_CHILD_PROJECTS = True
PAGE_SIZE = 200
COMMON_FILENAME = True
VERIFY_SSL = True

if getattr(sys, "frozen", False):
    # Running from PyInstaller EXE
    SCRIPT_FOLDER = Path(sys.executable).resolve().parent
else:
    # Running from .py
    SCRIPT_FOLDER = Path(__file__).resolve().parent

OUTPUT_FOLDER = SCRIPT_FOLDER / "output"
OUTPUT_FOLDER.mkdir(exist_ok=True)

if COMMON_FILENAME:
    OUTPUT_FILE = OUTPUT_FOLDER / f"Rally_Stories_and_Tasks_{TEAM_NAME}.csv"
else:
    OUTPUT_FILE = (
        OUTPUT_FOLDER
        / f"Rally_Stories_and_Tasks_{TEAM_NAME}_{datetime.now():%Y-%m-%d_%H-%M-%S}.csv"
    )

STORY_FETCH = (
    "ObjectID,FormattedID,Name,Description,ScheduleState,AcceptedDate,"
    "Owner,PlanEstimate,Iteration,Feature,Parent,Project,Blocked,LastUpdateDate"
)

TASK_FETCH = (
    "ObjectID,FormattedID,Name,Description,State,Estimate,ToDo,Actuals,"
    "Owner,WorkProduct,Project,LastUpdateDate"
)

OUTPUT_COLUMNS = [
    "Feature",
    "Parent Story",
    "Iteration",
    "Story ID",
    "Story Name",
    "Story Description",
    "Story State",
    "Story Owner",
    "Story Points",
    "Story Project",
    "Story Blocked",
    "Story Accepted Date",
    "Story Last Update",
    "Story ObjectID",
    "Task ID",
    "Task Name",
    "Task Description",
    "Task State",
    "Task Owner",
    "Task Estimate",
    "Task ToDo",
    "Task Actuals",
    "Task Project",
    "Task Last Update",
    "Task ObjectID",
    "Has Task",
    "Story Has No Tasks",
    "SearchText",
]


def clean_text(value):
    if value is None:
        return ""
    text = html.unescape(str(value))
    text = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def get_ref_name(value):
    return value.get("_refObjectName", "") if isinstance(value, dict) else ""


def get_ref_oid(value):
    if not isinstance(value, dict):
        return ""
    if value.get("ObjectID") is not None:
        return str(value["ObjectID"])
    match = re.search(r"/([^/?]+)(?:\?.*)?$", value.get("_ref", ""))
    return match.group(1) if match else ""


def keep_story(story):
    """
    Keep only non-Accepted stories.
    """

    state = str(story.get("ScheduleState", "")).strip().lower()

    if state == "accepted":
        return False

    return True


def create_ssl_context():
    return (
        ssl.create_default_context() if VERIFY_SSL else ssl._create_unverified_context()
    )


SSL_CONTEXT = create_ssl_context()


def rally_query(api_key, artifact_type, fetch, query=None, order=None):
    endpoint = f"{RALLY_BASE_URL}/{artifact_type}"
    headers = {
        "ZSESSIONID": api_key,
        "Accept": "application/json",
        "User-Agent": "RallyCSVExport/1.0",
    }
    start = 1
    all_results = []
    reported_total = None

    while True:
        params = {
            "workspace": f"/workspace/{WORKSPACE}",
            "project": f"/project/{PROJECT}",
            "projectScopeUp": "false",
            "projectScopeDown": "true" if INCLUDE_CHILD_PROJECTS else "false",
            "fetch": fetch,
            "pagesize": PAGE_SIZE,
            "start": start,
        }
        if query:
            params["query"] = query
        if order:
            params["order"] = order

        request = urllib.request.Request(
            endpoint + "?" + urllib.parse.urlencode(params),
            headers=headers,
            method="GET",
        )

        try:
            with urllib.request.urlopen(
                request, timeout=120, context=SSL_CONTEXT
            ) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Rally HTTP {error.code} for {artifact_type}: {detail}"
            ) from error
        except urllib.error.URLError as error:
            raise RuntimeError(f"Could not connect to Rally: {error.reason}") from error

        result = data.get("QueryResult", {})
        errors = result.get("Errors", [])
        if errors:
            raise RuntimeError(f"Rally errors for {artifact_type}: {'; '.join(errors)}")

        page = result.get("Results", [])
        if reported_total is None:
            reported_total = result.get("TotalResultCount", 0)
            print(f"{artifact_type} total reported by Rally: {reported_total}")

        if not page:
            break

        all_results.extend(page)
        print(f"{artifact_type}: downloaded {len(all_results)} of {reported_total}")

        if len(all_results) >= reported_total:
            break
        start += len(page)

    return all_results


def flatten_story(story):
    oid = story.get("ObjectID")
    return {
        "Feature": get_ref_name(story.get("Feature")),
        "Parent Story": get_ref_name(story.get("Parent")),
        "Iteration": get_ref_name(story.get("Iteration")),
        "Story ID": story.get("FormattedID", ""),
        "Story Name": story.get("Name", ""),
        "Story Description": clean_text(story.get("Description")),
        "Story State": story.get("ScheduleState", ""),
        "Story Owner": get_ref_name(story.get("Owner")),
        "Story Points": ""
        if story.get("PlanEstimate") is None
        else story.get("PlanEstimate"),
        "Story Project": get_ref_name(story.get("Project")),
        "Story Blocked": "" if story.get("Blocked") is None else story.get("Blocked"),
        "Story Accepted Date": story.get("AcceptedDate", "") or "",
        "Story Last Update": story.get("LastUpdateDate", "") or "",
        "Story ObjectID": str(oid) if oid is not None else "",
    }


def flatten_task(task):
    oid = task.get("ObjectID")
    return {
        "Task ID": task.get("FormattedID", ""),
        "Task Name": task.get("Name", ""),
        "Task Description": clean_text(task.get("Description")),
        "Task State": task.get("State", ""),
        "Task Owner": get_ref_name(task.get("Owner")),
        "Task Estimate": "" if task.get("Estimate") is None else task.get("Estimate"),
        "Task ToDo": "" if task.get("ToDo") is None else task.get("ToDo"),
        "Task Actuals": "" if task.get("Actuals") is None else task.get("Actuals"),
        "Task Project": get_ref_name(task.get("Project")),
        "Task Last Update": task.get("LastUpdateDate", "") or "",
        "Task ObjectID": str(oid) if oid is not None else "",
        "Story ObjectID": get_ref_oid(task.get("WorkProduct")),
    }


def blank_task():
    return {
        "Task ID": "",
        "Task Name": "",
        "Task Description": "",
        "Task State": "",
        "Task Owner": "",
        "Task Estimate": "",
        "Task ToDo": "",
        "Task Actuals": "",
        "Task Project": "",
        "Task Last Update": "",
        "Task ObjectID": "",
    }


def combine_stories_and_tasks(stories, tasks):
    task_map = {}
    for task in map(flatten_task, tasks):
        task_map.setdefault(task["Story ObjectID"], []).append(task)

    rows = []
    for story in map(flatten_story, stories):
        matches = task_map.get(story["Story ObjectID"], [])
        if matches:
            for task in matches:
                row = dict(story)
                task = dict(task)
                task.pop("Story ObjectID", None)
                row.update(task)
                row["Has Task"] = True
                row["Story Has No Tasks"] = False
                rows.append(row)
        else:
            row = dict(story)
            row.update(blank_task())
            row["Has Task"] = False
            row["Story Has No Tasks"] = True
            rows.append(row)
    return rows


def main():
    print("Rally Stories and Matched Tasks Export")
    print("======================================")
    print(f"Workspace ObjectID: {WORKSPACE}")
    print(f"Project ObjectID:   {PROJECT}")
    print(f"Team Name:          {TEAM_NAME}")

    # cutoff = subtract_calendar_months(datetime.now(timezone.utc), 1)
    # print(f"Accepted-story cutoff: {cutoff:%Y-%m-%d}")

    # api_key = getpass.getpass("Enter Rally API key: ").strip()
    if not API_KEY:
        raise RuntimeError("A Rally API key is required.")

    print("\nDownloading user stories...")
    downloaded_stories = rally_query(
        API_KEY, "hierarchicalrequirement", STORY_FETCH, order="Rank"
    )

    stories = [
        story
        for story in downloaded_stories
        if str(story.get("ScheduleState", "")).strip().lower() != "accepted"
    ]
    excluded = len(downloaded_stories) - len(stories)
    print(
        f"Stories retained: {len(stories)}; old Accepted stories excluded: {excluded}"
    )

    # Download tasks from the project scope, then keep only tasks linked
    # to the retained stories. This avoids Rally's fragile long OR queries.
    print("\nDownloading tasks from project scope...")
    all_tasks = rally_query(API_KEY, "task", TASK_FETCH)
    retained_story_oids = {
        str(story["ObjectID"]) for story in stories if story.get("ObjectID") is not None
    }
    tasks = [
        task
        for task in all_tasks
        if get_ref_oid(task.get("WorkProduct")) in retained_story_oids
    ]
    print(f"Tasks matched to retained stories: {len(tasks)}")

    rows = combine_stories_and_tasks(stories, tasks)
    OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)

    with OUTPUT_FILE.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=OUTPUT_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print("\nEXPORT COMPLETE")
    print(f"Stories initially downloaded: {len(downloaded_stories)}")
    print(f"Old Accepted stories excluded: {excluded}")
    print(f"Stories exported: {len(stories)}")
    print(f"Matched tasks exported: {len(tasks)}")
    print(f"CSV rows created: {len(rows)}")
    print(f"Saved file: {OUTPUT_FILE}")

    try:
        os.startfile(OUTPUT_FOLDER)
    except (AttributeError, OSError):
        pass


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nExport canceled.")
        sys.exit(1)
    except Exception as error:
        print("\nEXPORT FAILED")
        print("=============")
        print(error)
        sys.exit(1)
