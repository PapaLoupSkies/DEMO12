# Knowledge Platform

## Setup
```bash
pip install -r requirements.txt
python app.py
```

## Access
URL: http://localhost:5000

## Demo accounts (password: Pass1234!)
- superadmin       → Super Admin
- alice.martin     → Editor (Technology)
- carol.white      → Editor (Communication)
- hugo.moreau      → Editor (Risk & Compliance)
- bob.dupont       → Read Only
- grace.kim        → Read Only

## Structure
```
data/
├── master_data/       employees.csv
├── reference_data/    org_taxonomy, activity_taxonomy, content_categories, ...
├── catalog/           content_list, kpi_list, business_glossary, activity_communication, finished_documents
└── platform_data/     users, faq, events
```
