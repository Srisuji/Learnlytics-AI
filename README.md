# Learnlytics AI - Understand Performance. Unlock Potential.

An educational analytics web app (Streamlit + SQLite) designed for teachers, coordinators, and advisors. It brings attendance, academic marks, and assignment completion into one clear dashboard, flags students who may need extra support **with the transparent evidence behind each flag**, suggests practical study actions, and tracks faculty follow-ups.

> All demo data is **synthetic**. The support indicators are **for human review, not automated predictions**. The core app needs **no AI API key**.

---

## 🚀 For Beginners: Getting Started in 5 Steps

### On Windows (PowerShell)
1. Open PowerShell and navigate to the project directory:
   ```powershell
   cd c:\Users\gvsel\Downloads\edupulse-ai\edupulse-ai
   ```
2. Create a virtual environment:
   ```powershell
   python -m venv .venv
   ```
3. Activate the virtual environment:
   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```
4. Install the required dependencies:
   ```powershell
   pip install -r requirements.txt
   ```
5. Launch the application:
   ```powershell
   python -m streamlit run app.py
   ```
*(Alternatively, you can simply double-click `run_windows.bat` in File Explorer!)*

---

### On Mac / Linux (Terminal)
1. Open Terminal and navigate to the project folder:
   ```bash
   cd /path/to/edupulse-ai
   ```
2. Create a virtual environment:
   ```bash
   python3 -m venv .venv
   ```
3. Activate the virtual environment:
   ```bash
   source .venv/bin/activate
   ```
4. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
5. Start Learnlytics AI:
   ```bash
   python -m streamlit run app.py
   ```
*(Or run `bash run_mac_linux.sh` in your terminal!)*

---

## 🛠️ Troubleshooting

- **`streamlit` is not recognized as an internal or external command:**  
  Make sure your virtual environment is active (you should see `(.venv)` at the beginning of your command prompt). Also, launching with `python -m streamlit run app.py` instead of bare `streamlit run app.py` ensures the Python interpreter inside your active environment runs Streamlit directly.
- **PowerShell error: `Script execution disabled (PSSecurityException)`:**  
  Windows PowerShell restricts running scripts by default. To allow activating virtual environments for your user account, run:
  ```powershell
  Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
  ```
  Then re-run `.\.venv\Scripts\Activate.ps1`.
- **Port already in use (Address already in use / port 8501 taken):**  
  If another Streamlit process is running, you can run Streamlit on an alternate port:
  ```powershell
  python -m streamlit run app.py --server.port 8502
  ```
  Or close the terminal window running the previous session.


## Run the tests
```bash
python -m unittest discover -s tests -v      # no extra packages needed
# or
pytest -q
```
Tests use a temporary database, never your real one.

## Architecture
```
CSV upload / manual entry -> validation + duplicate checks -> SQLite (database.py)
      -> auth.py (PBKDF2-HMAC-SHA256, lockout, role enforcement)
      -> data_service.py (KPIs, filters, CRUD, import/export, student isolation)
      -> risk_engine.py (screening) -> recommendations.py (suggested actions)
      -> views_*.py (Role-based Streamlit pages: Admin, Staff, Student)
```
| File | Purpose |
|---|---|
| `app.py` | Entry point, login, first-run admin setup, role-based navigation |
| `auth.py` | PBKDF2 hashing, constant-time verification, lockout, user CRUD, preferences |
| `database.py` | Schema (`students`, `users`, `user_preferences`, etc.), idempotent seeding |
| `data_service.py` | CRUD, validation, CSV import/export, KPIs, interventions, role authorization |
| `risk_engine.py` | Rule-based screening score (documented + configurable) |
| `recommendations.py` | Rule-based recommendations; optional AI wording polish |
| `components.py` | Theme, KPI cards, badges, filters, display helpers |
| `views_*.py` | Modular views for Admin, Staff, and Student roles |
| `tests/` | Automated test suite (65 tests) |


## CSV schema
Required columns: `student_id, name, department, semester, attendance_rate, academic_score, assignment_rate`
Optional: `email, mentor`. Percentages are 0-100. Blank metrics are allowed and stored as *unavailable*
(never treated as zero). Duplicate IDs inside a file are rejected. IDs that already exist are skipped by
default (choose "update existing" to overwrite). A sample is in `data/sample_students.csv`.

## Risk-scoring formula (defaults, all editable in Settings)
| Indicator | Triggered when | Points |
|---|---|---|
| Attendance | below 75% | +30 |
| Academic score | below 50% | +35 |
| Assignment completion | below 60% | +20 |
| Score decline | dropped 10+ points across 3+ history records | +15 |

Categories: **Low** 0-24, **Medium** 25-49, **High** 50-74, **Critical** 75-100.
Missing values are "Unavailable", never failures. If all three core metrics are missing the result is
"Insufficient data". No sensitive attributes are used. These weights and thresholds are illustrative
defaults chosen for transparency; they are **not** statistically validated. Set values that match your
institution's policy.

## Privacy and security notes
- Synthetic data by default; nothing is sent to any external service by default.
- The student-portal selector is **demo-only**. Real deployments need authentication and server-side authorization.
- Optional AI wording polish (`.env.example`) sends only generic suggestion text, never student data.
- No secrets are hard-coded; use environment variables.

## Known limitations
- Single-user local prototype; no login or roles.
- On free cloud hosting the SQLite file can reset on restart - download a backup (Settings -> Backup).
- Rule thresholds are not validated against real outcomes.
- History-based trends only appear where weekly records exist.

## 5-minute demo script
1. Introduce the problem (scattered student data). 2. Show dashboard KPIs. 3. Search a student.
4. Open the profile. 5. Show which metrics triggered the flag. 6. Explain the category and its limits.
7. Open recommendations. 8. Record a faculty follow-up. 9. Show department analytics.
10. Download a report. 11. Explain privacy, human review and next steps.

## Deploy on Streamlit Community Cloud
1. Push this folder to a GitHub repository (the `.gitignore` already excludes the database and `.env`).
2. On share.streamlit.io choose the repo, branch and `app.py` as the main file.
3. Add any optional environment variables under *Secrets* / settings.
4. After deploying, open the public URL yourself and check every page before submitting.
