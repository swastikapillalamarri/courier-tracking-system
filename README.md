# Courier Tracking Management System

A simple web app to book couriers, update their delivery status and let
customers track a parcel with a tracking ID.

Built with **Python + Flask** (web pages) and **SQLite** (database, comes with Python).
Plain HTML and CSS for the design. No other frameworks.

## How to run

1. Install Python 3.8 or newer.
2. Open a terminal (Command Prompt) inside this folder and run:

       pip install flask
       python app.py

   On Windows you can also double-click `run.bat`.
3. Open http://127.0.0.1:5000 in your browser.

The database file `courier.db` is created automatically on the first run,
with 6 sample couriers. Delete that file any time to start fresh.

## Logins

| Who   | Page          | Username | Password |
|-------|---------------|----------|----------|
| Admin | /admin/login  | admin    | admin123 |
| User  | /login        | ravi     | user123  |

New users can create their own account from the "Create an account" link.

Sample tracking IDs: `CT10000001` (delivered), `CT10000003` (in transit), `CT10000006` (booked)

## Features

- **Opening animation** the first time the site is opened in a browser tab
- **Track a parcel** (no login): enter a tracking ID, see the progress line and full history
- **User sign-up, login and logout**: a user sees "My parcels", every courier sent from
  or coming to their phone number
- **Admin login and logout**, separate from the user login
- **Eye button** on every password box to show or hide the password
- **Dashboard** (admin): counts by status, search by ID / name / city, filter by status
- **Book a courier** (admin): form with validation, tracking ID generated automatically
- **Update status** (admin): Booked > Picked Up > In Transit > Out for Delivery > Delivered,
  with location and remarks saved to the history
- **Delete a courier** (admin)
- Passwords are stored hashed, never as plain text

## Files

    app.py               all the Python code (routes + database)
    requirements.txt     the one library needed (flask)
    run.bat              double-click starter for Windows
    templates/           HTML pages
    static/style.css     the design
    static/script.js     eye button and opening animation

## Database tables

- `users`: admin and user accounts (the `role` column tells them apart)
- `couriers`: one row per parcel (sender, receiver, route, weight, current status)
- `tracking_history`: one row per status update of a parcel
