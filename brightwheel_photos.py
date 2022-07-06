#!/usr/bin/env python3

import argparse
from datetime import datetime
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
    args = parser.parse_args()

    os.makedirs(args.directory, exist_ok=True)
    with requests.Session() as s:
        try:
            login(s, args.email, args.password)
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
        for activity in find_activities(s, student_id):
            # Skip if less than since argument
            if args.since:
                event_date = datetime.strptime(activity["event_date"][0:10], '%Y-%m-%d')
                since = datetime.strptime(args.since, '%Y-%m-%d')
                if event_date < since:
                    continue

            if activity["media"] is not None:
                url = activity["media"]["image_url"]
                r = s.get(url)
                image = Image.open(io.BytesIO(r.content))
                created_at = datetime.strptime(
                    activity["created_at"], "%Y-%m-%dT%H:%M:%S.%f%z"
                )
                comment = activity["note"]
                exif = build_exif_bytes(image, created_at, comment)
                path = urlparse(url).path.split("/")[-1][:-4]
                image.save(
                    "{directory}/{path}.jpg".format(directory=args.directory, path=path),
                    exif=exif,
                )
            elif activity["video_info"] is not None:
                url = activity["video_info"]["downloadable_url"]
                r = s.get(url, stream=True)
                path = urlparse(url).path.split("/")[-1][:-4]
                with open("{directory}/{path}.mp4".format(directory=args.directory, path=path), "wb") as f:
                    for chunk in r.iter_content(chunk_size=128):
                        f.write(chunk)


def login(s, email, password):
    """Login to Brightwheel and update the given requests session"""
    # login
    login_data = {"user": {"email": email, "password": password}}
    headers = {
        "X-Client-Name": "web",
        "X-Client-Version": "b15cec31e66fa803de35b53260872aa7e5e84e29",
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
    """Generator that returns all photo and video activities for the given student"""
    action_types = ['ac_video', 'ac_photo']
    page_size = 10
    params = {
        "page_size": page_size,
        "include_parent_actions": "true",
    }
    for action_type in action_types:
        params["action_type"] = action_type
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
    """Given an image, acreated date, and a comment, builds EXIF byte buffer"""
    exif_date = created_date.strftime("%Y:%m:%d %H:%M:%S")
    try:
        exif = piexif.load(image.info["exif"])
    except KeyError:
        exif = {"0th": {}, "Exif": {}}
    exif["0th"][piexif.ImageIFD.DateTime] = exif_date.encode("utf-8")
    exif["Exif"][piexif.ExifIFD.DateTimeOriginal] = exif_date.encode("utf-8")
    exif["Exif"][piexif.ExifIFD.DateTimeDigitized] = exif_date.encode("utf-8")
    if comment:
        exif["0th"][piexif.ImageIFD.ImageDescription] = comment.encode("utf-8")
    return piexif.dump(exif)


if __name__ == "__main__":
    main()
