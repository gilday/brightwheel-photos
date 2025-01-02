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
    """Runs brightwheel_photos cli"""
    parser = argparse.ArgumentParser(description="Download photos from Brightwheel")
    parser.add_argument(
        "--email", required=True, help="email used for Brightwheel account"
    )
    parser.add_argument(
        "--password", required=True, help="password used for Brightwheel account"
    )
    parser.add_argument(
        "--directory", required=True, help="directory in which to save the photos"
    )
    parser.add_argument("--student-id", help="Brightwheel student ID")
    parser.add_argument("--since", help="Skip any photos before a given YYYY-MM-DD")
    parser.add_argument("--before", help="Skip any photos after a given YYYY-MM-DD")
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip any existing photos or videos",
    )
    args = parser.parse_args()

    os.makedirs(args.directory, exist_ok=True)
    with requests.Session() as s:
        try:
            twofacode = trigger_2fa(s, args.email, args.password)
            login(s, args.email, args.password, twofacode)
        except requests.HTTPError as err:
            if [err.response.status_code == 401]:
                print("Login failed", file=sys.stderr)
                sys.exit(1)
        # try to find student_id if not provided
        student_id = args.student_id
        if not student_id:
            students = find_students(s)
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

        # find and save all photos for the student
        with open(f"student-{student_id}-activities.jsonl", "w") as raw_fh:
            for activity in find_activities(s, student_id):
                json.dump(activity, raw_fh)
                raw_fh.write("\n")
                # Skip if less than since argument
                if args.since:
                    event_date = datetime.strptime(activity["event_date"][0:10], "%Y-%m-%d")
                    since = datetime.strptime(args.since, "%Y-%m-%d")
                    if event_date < since:
                        continue

                # Skip if greater than before argument
                if args.before:
                    event_date = datetime.strptime(activity["event_date"][0:10], "%Y-%m-%d")
                    before = datetime.strptime(args.before, "%Y-%m-%d")
                    if event_date > before:
                        continue

                if activity["media"] is not None:
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
                        continue

                    # grab it
                    r = s.get(url)
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
                elif activity["video_info"] is not None:
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
                        continue

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
    r = s.post(
        "https://schools.mybrightwheel.com/api/v1/sessions/start",
        headers=headers,
        json=login_data,
    )
    r.raise_for_status()
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
    r = s.post(
        "https://schools.mybrightwheel.com/api/v1/sessions",
        headers=headers,
        json=login_data,
    )
    r.raise_for_status()
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
