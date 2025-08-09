# Brightwheel Photos

Python script for downloading a student's photos and videos from
[Brightwheel](https://schools.mybrightwheel.com).

My kid went to a daycare that used Brightwheel to communicate with parents and
guardians. The teachers sent plenty of photos using Brightwheel. This script
downloads them all so I can keep them.

Each photo's EXIF data includes the original creation date and any message
attached to the photo as a comment.

## Use

Install with `pipx install brightwheel-photos`

### Using Environment Variables (Recommended)

For better security and convenience, you can store your credentials in a `.env` file:

1. Copy the example environment file:
   ```sh
   cp .env.example .env
   ```

2. Edit `.env` and add your credentials:
   ```env
   BRIGHTWHEEL_EMAIL=your.email@example.com
   BRIGHTWHEEL_PASSWORD=your_password_here
   BRIGHTWHEEL_DIRECTORY=~/Photos/brightwheel
   # Optional: specify student ID if you have multiple students
   # BRIGHTWHEEL_STUDENT_ID=student_id_here
   ```

3. Run the tool (it will automatically load credentials from `.env`):
   ```sh
   brightwheel-photos
   ```

### Using Command Line Arguments

Alternatively, you can provide credentials via command line:

```sh
brightwheel-photos --email <brightwheel-account-email> --password <brightwheel-account-password> --directory ~/Photos/brightwheel
```

Note: Command line arguments will override any values set in the `.env` file.

The program will exit when all the photos have been saved.
