#!/usr/bin/env python3

import argparse
import json
from datetime import datetime, timezone
import io
import os
import sys
from urllib.parse import urlparse
import piexif
from PIL import Image
import requests


def main():
    """Runs brightwheel babybuddy sync cli"""
    parser = argparse.ArgumentParser(description="Download data from Brightwheel")
    parser.add_argument(
        "--email", required=True, help="email used for Brightwheel account"
    )
    parser.add_argument(
        "--password", required=True, help="password used for Brightwheel account"
    )
    parser.add_argument(
        "--directory", required=True, help="directory in which to save the photos"
    )
    parser.add_argument("--babybuddy_url", required=True, help="Base URL of your babybuddy instance, such as https://baby.example.com")
    parser.add_argument("--babybuddy_token", required=True, help="A user's Baby Buddy token from their user settings page, a 40 character string")
    parser.add_argument("--babybuddy_child_id", required=True, help="A child's ID, typically 1")
    parser.add_argument("--student-id", help="Brightwheel student ID")
    parser.add_argument("--since", help="Skip any data before a given YYYY-MM-DD")
    parser.add_argument("--before", help="Skip any data after a given YYYY-MM-DD")
    parser.add_argument("--skip-existing",action="store_true",help="Skip any existing photos, videos, and other data")
    parser.add_argument("--ignore-errors",action="store_true",help="When an HTTP 400 code is returned from babybuddy, ignore it")
    args = parser.parse_args()

    #Directory for media
    os.makedirs(args.directory, exist_ok=True)

    #temporary variables for babybuddy data
    ins_outs = [] #Each element is dict like {"event_date": "2025-08-01T21:59:45.908Z", "checkin": True, "dropoff_report": "string"}
    naps = [] #Each element is dict like {"event_date": "2025-08-01T21:59:45.908Z", "wake": True, "note": "A note"}
    with requests.Session() as brightwheel_session:
        try:
            twofacode = trigger_2fa(brightwheel_session, args.email, args.password)
            login(brightwheel_session, args.email, args.password, twofacode)
        except requests.HTTPError as err:
            if [err.response.status_code == 401]:
                print(f"Login failed {err}", file=sys.stderr)
                sys.exit(1)
        # try to find student_id if not provided
        student_id = args.student_id
        if not student_id:
            students = find_students(brightwheel_session)
            if len(students) > 1:
                print("Multiple students detected: pick one", file=sys.stderr)
                for student in students:
                    print(
                        "{} {} {}".format(
                            student["object_id"],
                            student["first_name"],
                            student["last_name"],
                            file=sys.stderr,
                        )
                    )
                sys.exit(1)
            student_id = students[0]["object_id"]
        with requests.Session() as babybuddy_session:
            # find and save all data for the student
            with open(f"student-{student_id}-activities.jsonl", "w") as raw_fh:
                for activity in find_activities(brightwheel_session, student_id):
                    json.dump(activity, raw_fh)
                    raw_fh.write("\n")
                    # Skip if less than since argument
                    if args.since:
                        event_date = datetime.strptime(activity["event_date"][0:10], "%Y-%m-%d")
                        since = datetime.strptime(args.since, "%Y-%m-%d")
                        if event_date < since:
                            break #Brightwheel returns events in chronological order, so once we get here we don't need to keep iterating
                    # Skip if greater than before argument
                    if args.before:
                        event_date = datetime.strptime(activity["event_date"][0:10], "%Y-%m-%d")
                        before = datetime.strptime(args.before, "%Y-%m-%d")
                        if event_date > before:
                            continue
                    try:
                        if activity["media"] is not None:
                            handle_photo(activity, args, brightwheel_session)
                        elif activity["video_info"] is not None:
                            handle_video(activity, args)
                        elif activity["action_type"] == "ac_checkin":
                            #"state" is "1" for checkin, "2 " for checkout. dropoff_report and health_screen_display is populated for checkins
                            ins_outs.append( {"event_date": activity["event_date"], "checkin": True if activity["state"]=="1" else False, "dropoff_report": activity["dropoff_report"]})
                        elif activity["action_type"] == "ac_food":
                            handle_food(activity, args, babybuddy_session)
                        elif activity["action_type"] == "ac_nap":
                            # "state" is "0" for wake up, "1" for fall asleep, duration has to be calculated manually
                            naps.append({"event_date": activity["event_date"], "wake": activity["state"]=="0", "note": activity["note"]})
                        elif activity["action_type"] == "ac_potty":
                            handle_potty(activity, args, babybuddy_session)
                        elif activity["action_type"] == "ac_observation":
                            handle_observation(activity, args, babybuddy_session)
                    except requests.exceptions.HTTPError as e:
                        if args.ignore_errors and e.response.status_code == 400:
                            print(f"Ignoring exception {e}, assuming event is already in Baby Buddy")
                        else:
                            raise
            handle_ins_and_outs(ins_outs, babybuddy_session, args)
            handle_naps(naps, babybuddy_session, args)

def handle_observation(activity, args, babybuddy_session):
    # "note" includes teacher note
    # "observation_milestones" is a huge structure of all possible milestones, not sure how they are selected
    headers = {"Content-Type": "application/json",
                "Authorization": f"Token {args.babybuddy_token}"}
    post_content = {"child": args.babybuddy_child_id,
                "time": activity["event_date"],
                "tags": ["Brightwheel"],
                "note": f"Imported from Brightwheel: Observation: {activity["note"]}"}
    if args.skip_existing:
        #check if this event already exists
        params = {"limit": 1, "child": args.babybuddy_child_id, "date": activity["event_date"], "tags": ["Brightwheel"]}
        r = babybuddy_session.get(f"{args.babybuddy_url}/api/notes/", headers=headers, params=params)
        response_json = r.json()
        if response_json["count"] > 0:
            print(f"Skipping creating note because it already exists: {post_content}")
            return
        else:
            print(f"Observation does not yet exist")
    print(f"Creating note: {post_content}")
    
    r = babybuddy_session.post(f"{args.babybuddy_url}/api/notes/", headers=headers, json=post_content)
    r.raise_for_status()
def handle_potty(activity, args, babybuddy_session):
    #"details_blob": {
    #        "potty": "wet", #or "nothing"
    #        "potty_type": "diaper",
    #        "potty_extras": [
    #          "wet",
    #          "bm"
    #        ]
    #      },
    headers = {"Content-Type": "application/json",
                "Authorization": f"Token {args.babybuddy_token}"}
    is_wet = "wet" in activity["details_blob"]["potty_extras"]
    is_bowel_movement = "bm" in activity["details_blob"]["potty_extras"]
    post_content = {"child": args.babybuddy_child_id,
                "time": activity["event_date"],
                "wet": is_wet,
                "solid": is_bowel_movement,
                "tags": ["Brightwheel"],
                "notes": f"Imported from Brightwheel: {activity["note"]}"}
    if args.skip_existing:
        #check if this event already exists
        params = {"limit": 1, "child": args.babybuddy_child_id, "date": activity["event_date"], "tags": ["Brightwheel"]}
        r = babybuddy_session.get(f"{args.babybuddy_url}/api/changes/", headers=headers, params=params)
        response_json = r.json()
        print(response_json)
        if response_json["count"] > 0:
            print(f"Skipping creating potty because it already exists: {post_content}")
            return
        else:
            print(f"Potty does not yet exist")
    print(f"Creating potty: {post_content}")
    r = babybuddy_session.post(f"{args.babybuddy_url}/api/changes/", headers=headers, json=post_content)
    r.raise_for_status()
def handle_food(activity, args, babybuddy_session):
    #"details_blob": {
    #  "amount": 4, #or 1 for solids
    #  "food_type": "bottle", #or "food"
    #  "amount_type": "ounce", #or ""
    #  "food_meal_type": -1 #or 2 or 3, not sure what these mean
    #},

    #  "menu_item_tags": [
    #    {
    #      "object_id": "0a85e698-dbbe-4e25-876e-f52ed81b5543",
    #      "name": "blueberries",
    #      "tag_type": "menu_item"
    #    },
    #    {
    #      "object_id": "62078023-2ad0-4cea-986d-758a226e7e1b",
    #      "name": "broccoli",
    #      "tag_type": "menu_item"
    #    }
    #  ]
    #},
    menu = [item["name"] for item in activity["menu_item_tags"]]
    headers = {"Content-Type": "application/json",
            "Authorization": f"Token {args.babybuddy_token}"}
    is_milk = activity["details_blob"]["food_type"]=="bottle"
    post_content = {"child": args.babybuddy_child_id,
                "start": activity["event_date"],
                "end": activity["event_date"],
                "type": "breast milk" if is_milk else "solid food",
                "method": "bottle" if is_milk else "self fed",
                "amount": activity["details_blob"]["amount"],
                "tags": ["Brightwheel"],
                "notes": f"Imported from Brightwheel: {activity["note"]}\n\n{','.join(menu)}"}

    print(f"Creating feeding: {post_content}")
    if args.skip_existing:
        #check if this event already exists
        params = {"limit": 1, "child": args.babybuddy_child_id, "start": activity["event_date"], "end": activity["event_date"], "tags": ["Brightwheel"]}
        r = babybuddy_session.get(f"{args.babybuddy_url}/api/feedings/", headers=headers, params=params)
        response_json = r.json()
        if response_json["count"] > 0:
            print(f"Skipping creating feeding because it already exists: {post_content}")
            return
        else:
            print(f"Feeding does not yet exist")
    r = babybuddy_session.post(f"{args.babybuddy_url}/api/feedings/", headers=headers, json=post_content)
    r.raise_for_status()
def handle_ins_and_outs(ins_outs, babybuddy_session, args):
            print(f"Ins and outs: {ins_outs}")
            in_out_iter = iter(enumerate(ins_outs))
            for index,in_out in in_out_iter:
                if in_out["checkin"]:
                    print(f"Mismatched number of check ins/outs, this one will be skipped: {in_out}")
                    continue
                if len(ins_outs) >= index + 2: #e.g. index == 0 for the first checkout, must have at least two in the array to continue processing
                    #See if the next checkin matches this one
                    in_event = ins_outs[index+1]
                    out_event = in_out
                    if in_event["checkin"] and not out_event["checkin"]:
                        in_date = in_event["event_date"]
                        out_date = out_event["event_date"]
                        dropoff_report = in_event["dropoff_report"]

                        headers = {"Content-Type": "application/json",
                                   "Authorization": f"Token {args.babybuddy_token}"}
                        print(in_date)
                        print(out_date)
                        print(dropoff_report)
                        if(dropoff_report):
                            if dropoff_report["woke_up"] is None:
                                print("Dropoff wake time not populated, using event date")
                                dropoff_report["woke_up"] = in_date
                            if dropoff_report["last_ate"] is None:
                                print("Last ate time not populated, using event date")
                                dropoff_report["last_ate"] = in_date
                            if dropoff_report["last_potty"] is None:
                                print("Last potty time not populated, using event date")
                                dropoff_report["last_potty"] = in_date
                            note = f"Imported from Brightwheel: daycare check in at: {utc_to_local(in_date)}, check out at: {utc_to_local(out_date)}.\nDropoff report:\n    Woke up at: {utc_to_local(dropoff_report["woke_up"])}\n    Last ate at: {utc_to_local(dropoff_report["last_ate"])}\n    Last potty: {utc_to_local(dropoff_report["last_potty"])}\n    Pickup time: {utc_to_local(dropoff_report["pickup_time"])}"
                        else:
                            note = f"Imported from Brightwheel: daycare check in at: {utc_to_local(in_date)}, check out at: {utc_to_local(out_date)}.\nDropoff report was blank"
                        post_content = {"child": args.babybuddy_child_id,
                                    "time": out_date,
                                    "tags": ["Brightwheel"],
                                    "note": note}
                        if args.skip_existing:
                            #check if this event already exists
                            params = {"limit": 1, "child": args.babybuddy_child_id, "date": out_date, "tags": ["Brightwheel"]}
                            r = babybuddy_session.get(f"{args.babybuddy_url}/api/notes/", headers=headers, params=params)
                            response_json = r.json()
                            if response_json["count"] > 0:
                                print(f"Skipping creating dropoff because it already exists: {post_content}")
                                next(in_out_iter)
                                continue
                            else:
                                print(f"Dropoff does not yet exist")
                        print(f"Creating dropoff: {post_content}")
                        
                        try:
                            r = babybuddy_session.post(f"{args.babybuddy_url}/api/notes/", headers=headers, json=post_content)
                            r.raise_for_status()
                        except requests.exceptions.HTTPError as e:
                            if args.ignore_errors and e.response.status_code == 400:
                                print(f"Ignoring exception {e}, assuming event is already in Baby Buddy")
                            else:
                                raise
                    else:
                        print(f"Mismatched checkins expected in to be: {in_event} and out to be: {out_event}")
                    #Skip the next event, it has already been handled
                    next(in_out_iter)

def handle_naps(naps, babybuddy_session, args):
            print(f"Naps: {naps}")
            naps_iter = iter(enumerate(naps))
            for index,nap in naps_iter:
                if not nap["wake"]:
                    print(f"Mismatched number of naps, this one will be skipped: {nap}")
                    continue
                if len(naps) >= index + 2: #e.g. index == 0 for the first nap, must have at least two in the array to continue processing
                    #See if the next nap matches this one
                    sleep_event = naps[index+1]
                    wake_event = nap
                    if wake_event["wake"] and not sleep_event["wake"]:
                        sleep_date = sleep_event["event_date"]
                        wake_date = wake_event["event_date"]
                        notes = ""
                        if sleep_event["note"] and len(sleep_event["note"]) > 0:
                            notes += f"Start nap note: {sleep_event["note"]}"
                        if wake_event["note"] and len(wake_event["note"]) > 0:
                            notes += (" " if len(notes) > 0 else "") + f"End nap note: {wake_event["note"]}"

                        headers = {"Content-Type": "application/json",
                                   "Authorization": f"Token {args.babybuddy_token}"}
                        post_content = {"child": args.babybuddy_child_id,
                                    "start": sleep_date,
                                    "end": wake_date, #############################################
                                    "nap": True,
                                    "tags": ["Brightwheel"],
                                    "notes": "Imported from Brightwheel: " + (notes if len(notes) > 0 else "No notes from daycare")}
                        if args.skip_existing:
                            #check if this event already exists
                            params = {"limit": 1, "child": args.babybuddy_child_id, "start": sleep_date, "end": wake_date, "tags": ["Brightwheel"]}
                            r = babybuddy_session.get(f"{args.babybuddy_url}/api/sleep/", headers=headers, params=params)
                            response_json = r.json()
                            if response_json["count"] > 0:
                                print(f"Skipping creating nap because it already exists: {response_json} <<>> {post_content}")
                                next(naps_iter)
                                continue
                            else:
                                print(f"Nap does not yet exist")
                        print(f"Creating nap: {post_content}")
                        
                        try:
                            r = babybuddy_session.post(f"{args.babybuddy_url}/api/sleep/", headers=headers, json=post_content)
                            r.raise_for_status()
                        except requests.exceptions.HTTPError as e:
                            if args.ignore_errors and e.response.status_code == 400:
                                print(f"Ignoring exception {e}, assuming event is already in Baby Buddy")
                            else:
                                raise
                    else:
                        print(f"Mismatched checkins expected wake to be: {wake_event} and sleep to be: {sleep_event}")
                    #Skip the next event, it has already been handled
                    next(naps_iter)
def utc_to_local(timestamp):
    """timestamp must be formatted like 2025-08-09T00:09:16.856Z"""
    #From: https://stackoverflow.com/a/46339491/1937630

    d=datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S.%fZ") #Get your naive datetime object
    d=d.replace(tzinfo=timezone.utc) #Convert it to an aware datetime object in UTC time.
    d=d.astimezone() #Convert it to your local timezone (still aware)
    return d.__str__()

def handle_photo(activity, args, brightwheel_session):
    url = activity["media"]["image_url"]
    path = urlparse(url).path.split("/")[-1][:-4]
    created_at = datetime.strptime(
        activity["created_at"], "%Y-%m-%dT%H:%M:%S.%f%z"
    )
    if args.skip_existing is True and os.path.isfile(
        f"{args.directory}/{path}.jpg"
    ):
        print(
            f"skipping download of photo {created_at}, file exists already"
        )

    # grab it
    r = brightwheel_session.get(url)
    image = Image.open(io.BytesIO(r.content))
    comment = activity["note"]
    exif = build_exif_bytes(image, created_at, comment)
    image.save(
        "{directory}/{path}.jpg".format(
            directory=args.directory, path=path
        ),
        exif=exif,
    )
    print(f"downloaded photo from {created_at}")

def handle_video(activity, args):
    url = activity["video_info"]["downloadable_url"]
    path = urlparse(url).path.split("/")[-1][:-4]
    created_at = datetime.strptime(
        activity["created_at"], "%Y-%m-%dT%H:%M:%S.%f%z"
    )
    if args.skip_existing is True and os.path.isfile(
        f"{args.directory}/{path}.mp4"
    ):
        print(
            f"skipping download of video {created_at}, file exists already"
        )

    # grab it -- for some reason we need to use a new session to
    # get the video content; using the existing session results
    # in a permission denied error
    with requests.Session() as vs:
        r = vs.get(url, stream=True)
        with open(
            "{directory}/{path}.mp4".format(
                directory=args.directory, path=path
            ),
            "wb",
        ) as f:
            for chunk in r.iter_content(chunk_size=128):
                f.write(chunk)
            print(f"downloaded video from {created_at} from {url}")

def trigger_2fa(s, email, password):
    """Trigger sending the 2FA login code"""
    login_data = {"user": {"email": email, "password": password}}
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Sec-Fetch-Site": "same-origin",
        "Accept-Language": "en",
        "Accept-Encoding": "gzip, deflate, br",
        "Sec-Fetch-Mode": "cors",
        "Host": "schools.mybrightwheel.com",
        "Origin": "https://schools.mybrightwheel.com",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5.2 Safari/605.1.15",
        "Referer": "https://schools.mybrightwheel.com/sign-in",
        "Sec-Fetch-Dest": "empty",
        "X-Client-Name": "web",
        "X-Client-Version": "225",
    }
    print("Checking for two factor")
    r = s.post(
        "https://schools.mybrightwheel.com/api/v1/sessions/start",
        headers=headers,
        json=login_data,
    )
    print("Finished two factor check")
    r.raise_for_status()
    print("Two factor check success")
    data = r.json()
    if data["2fa_required"] == True:
        print(f'2FA required, code sent to {data["2fa_code_sent_to"][0]}')
        twofacode = input("Enter 2FA code: ")
        return twofacode
    return None


def login(s, email, password, twofacode=None):
    """Login to Brightwheel and update the given requests session"""
    # login
    login_data = {"user": {"email": email, "password": password}}
    if not twofacode is None:
        login_data["2fa_code"] = twofacode

    headers = {
        "Accept": "application/json, text/plain, */*",
        "Sec-Fetch-Site": "same-origin",
        "Accept-Language": "en",
        "Accept-Encoding": "gzip, deflate, br",
        "Sec-Fetch-Mode": "cors",
        "Host": "schools.mybrightwheel.com",
        "Origin": "https://schools.mybrightwheel.com",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5.2 Safari/605.1.15",
        "Referer": "https://schools.mybrightwheel.com/sign-in",
        "X-Client-Name": "web",
        "X-Client-Version": "225",
    }
    print("Attempting login")
    r = s.post(
        "https://schools.mybrightwheel.com/api/v1/sessions",
        headers=headers,
        json=login_data,
    )
    print("Login request sent")
    r.raise_for_status()
    print("Logged in")
    csrf_token = r.json()["csrf"]
    headers["X-CSRF-Token"] = csrf_token
    s.headers.update(headers)


def find_students(s):
    """Returns a list of all students associated with the account"""
    headers = {"Accept": "application/json"}
    r = s.get("https://schools.mybrightwheel.com/api/v1/users/me", headers=headers)
    r.raise_for_status()
    guardian_id = r.json()["object_id"]

    r = s.get(
        "https://schools.mybrightwheel.com/api/v1/guardians/{}/students".format(
            guardian_id
        )
    )
    return [record["student"] for record in r.json()["students"]]


def find_activities(s, student_id):
    """Generator that returns all activities for the given student"""
    page_size = 10
    params = {
        "page_size": page_size,
        "include_parent_actions": "true",
    }
    page = 0

    while True:
        params["page"] = page
        params["offset"] = page * page_size
        r = s.get(
            "https://schools.mybrightwheel.com/api/v1/students/{}/activities".format(
                student_id
            ),
            params=params,
        )
        data = r.json()
        activities = data["activities"]
        if len(activities) <= 0:
            break
        for activity in activities:
            yield activity
        page += 1


def build_exif_bytes(image, created_date, comment):
    """Given an image, a created date, and a comment, builds EXIF byte buffer"""
    exif_date_utc_colons = created_date.astimezone(timezone.utc).strftime(
        "%Y:%m:%d %H:%M:%S"
    )
    exif_offset_utc = "+00:00"
    try:
        exif = piexif.load(image.info["exif"])
    except KeyError:
        exif = {"0th": {}, "Exif": {}}
    exif["0th"][piexif.ImageIFD.DateTime] = exif_date_utc_colons.encode("utf-8")
    exif["0th"][piexif.ImageIFD.TimeZoneOffset] = exif_offset_utc.encode("utf-8")
    exif["Exif"][piexif.ExifIFD.OffsetTime] = exif_offset_utc.encode("utf-8")

    exif["Exif"][piexif.ExifIFD.DateTimeOriginal] = exif_date_utc_colons.encode("utf-8")
    exif["Exif"][piexif.ExifIFD.OffsetTimeOriginal] = exif_offset_utc.encode("utf-8")

    exif["Exif"][piexif.ExifIFD.DateTimeDigitized] = exif_date_utc_colons.encode(
        "utf-8"
    )
    exif["Exif"][piexif.ExifIFD.OffsetTimeDigitized] = exif_offset_utc.encode("utf-8")

    if comment:
        exif["0th"][piexif.ImageIFD.ImageDescription] = comment.encode("utf-8")
    return piexif.dump(exif)


if __name__ == "__main__":
    main()
