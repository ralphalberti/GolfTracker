# Golf Tracker Project

## 📌 Versioning Workflow

This project uses a **manual versioning scheme** (Git-lite) to keep development safe and organized.

### 🔑 Files
- **golf_tracker_gold.py**  
  The stable "gold standard" baseline. Only updated when explicitly promoted.

- **golf_tracker_XX.py**  
  Numbered working versions (e.g., `golf_tracker_60.py`, `golf_tracker_61.py`).  
  Each change increments the version number automatically.

- **CHANGELOG.txt**  
  Records what was added/changed in each version. Updated automatically.

- **settings.json**  
  Stores UI/window preferences.

### 🚀 Workflow
1. When changes are made, a new file is saved with the next version number.  
   Example: `golf_tracker_61.py` → `golf_tracker_62.py`.

2. `CHANGELOG.txt` is updated automatically with a template entry for the new version.

3. To make a version the new baseline:  
   ```
   promote vXX to gold
   ```
   This copies `golf_tracker_XX.py` to `golf_tracker_gold.py`.

### 📁 Example Directory
```
/golf_tracker/
  ├── golf_tracker_gold.py
  ├── golf_tracker_60.py
  ├── golf_tracker_61.py
  ├── CHANGELOG.txt
  ├── README.md
  └── settings.json
```

---

✅ With this setup, you can experiment freely, always knowing you have a **stable gold file** to fall back on.
