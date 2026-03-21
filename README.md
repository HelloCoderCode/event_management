#  Eventify – Event Management System

A complete Event Management System built using Django where users can explore events and book tickets, while organizers can create and manage events.

---

##  Features

###  Attendee (No Login Required)

* View all events
* See event details and ticket types
* Select ticket quantity (+ / - UI)
* Register with details (Name, Email, Phone, etc.)
* Get booking confirmation
* QR Code generation for tickets
* Download PDF ticket
* Email confirmation

---

###  Organizer

* Register & Login
* Create and manage events
* Add custom ticket types (Free, VIP, etc.)
* Define registration fields
* View all registrations
* Export data as CSV

---

###  Admin Panel

* Full control over:

  * Events
  * Tickets
  * Users
  * Registrations

---

##  Tech Stack

* Backend: Django (Python)
* Frontend: HTML, CSS, JavaScript
* Database: SQLite
* Libraries:

  * Pillow (Image handling)
  * qrcode (QR generation)
  * reportlab (PDF tickets)

---

##  Project Setup

###  1. Clone Repository

```bash
git clone https://github.com/SoftwareTechnology-Hub/event_management.git
cd event_management/event_management
```

---

###  2. Create Virtual Environment

```bash
python -m venv env
```

---

###  3. Activate Environment

#### Windows:

```bash
env\Scripts\activate
```

#### Linux/Mac:

```bash
source env/bin/activate
```

---

###  4. Install Dependencies

```bash
pip install -r requirements.txt
```

---

###  5. Run Migrations

```bash
python manage.py makemigrations
python manage.py migrate
```

---

###  6. Create Superuser

```bash
python manage.py createsuperuser
```

---

###  7. Run Server

```bash
python manage.py runserver
```

---

###  8. Open in Browser

* Home: http://127.0.0.1:8000/
* Admin: http://127.0.0.1:8000/admin/

---

##  Project Structure

```
event_management/
│
├── event_management/   # Main project settings
├── events/             # Event & ticket logic
├── users/              # Authentication & user logic
├── templates/          # HTML templates
├── static/             # CSS, JS, Images
├── manage.py
└── requirements.txt
```

---

##  Notes

* Always run commands where `manage.py` exists
* Use virtual environment to avoid dependency conflicts
* Ignore warning related to `moviepy` (not used in project)

---

##  Future Enhancements

* Online payment integration
* Email verification system
* Mobile responsive UI
* Event analytics dashboard

---

##  Author

Developed by SoftwareTechnology-Hub 

---

Happy Coding!
