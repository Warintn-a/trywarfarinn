from flask import Flask, request, abort
from linebot.v3.messaging import (
    MessagingApi, Configuration, ApiClient,FlexMessage,
    TextMessage, MessageAction, CarouselColumn, CarouselTemplate, TemplateMessage, ReplyMessageRequest
)
from linebot.v3.webhook import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from linebot.models import QuickReplyButton, PostbackAction
import os
import re
import math
import random
import logging
from datetime import datetime, timedelta

DRUG_DATABASE = {
    "Amoxicillin": {
        "concentration_mg_per_ml": 250 / 5,
        "bottle_size_ml": 60,
        "indications": {
            "Pharyngitis/Tonsillitis": [
                {
                    "sub_indication": "Group A Streptococcus",
                    "dose_mg_per_kg_per_day": 50,
                    "frequency": [1, 2],
                    "duration_days": 10,
                    "max_mg_per_day": 1000,
                    "note": "📌 ใช้ได้ทั้งแบบวันละครั้งหรือแบ่งวันละ 2 ครั้ง × 10 วัน ตามความสะดวก"
                }
            ],
            "Acute Otitis Media (AOM)": [
                {
                    "label": "High-dose regimen",
                    "dose_mg_per_kg_per_day": [80, 90],
                    "frequency": 2,
                    "duration_days": 10,
                    "max_mg_per_day": 4000,
                    "note": "เหมาะในสหรัฐอเมริกา หรือเมื่อมี S. pneumoniae ดื้อเพนนิซิลลิน"
                },
                {
                    "label": "Standard-dose regimen",
                    "dose_mg_per_kg_per_day": [40, 50],
                    "frequency": 2,
                    "duration_days": 7,
                    "max_mg_per_day": 1500,
                    "note": "ใช้ได้เฉพาะในพื้นที่ที่เชื้อ S. pneumoniae ดื้อต่อ penicillin < 10% เท่านั้น"
                }
            ],
            "Pneumonia (community acquired)": [
                {
                    "label": "Empiric therapy (bacterial pneumonia)",
                    "dose_mg_per_kg_per_day": 90,
                    "frequency": 2,
                    "duration_days": 5,
                    "max_mg_per_day": 4000
                },
                {
                    "label": "Group A Streptococcus, mild",
                    "dose_mg_per_kg_per_day": [50, 75],
                    "frequency": 2,
                    "duration_days": 7,
                    "max_mg_per_day": 4000
                },
                {
                    "label": "H. influenzae, mild",
                    "dose_mg_per_kg_per_day": [75, 100],
                    "frequency": 3,
                    "duration_days": 7,
                    "max_mg_per_day": 4000
                },
                {
                    "label": "S. pneumoniae, MIC ≤2",
                    "dose_mg_per_kg_per_day": 90,
                    "frequency": [2, 3],
                    "duration_days": 7,
                    "max_mg_per_day": 4000,
                    "note": "เลือกความถี่ตาม MIC: 12 ชม หรือ 8 ชม"
                },
                {
                    "label": "S. pneumoniae, MIC = 2 mcg/mL",
                    "dose_mg_per_kg_per_day": [90, 100],
                    "frequency": 3,
                    "duration_days": 7,
                    "max_mg_per_day": 4000,
                    "note": "ใช้เพื่อให้ time > MIC ได้ตามเป้าหมาย"
                }
            ],
            "Anthrax": [
                {
                    "title": "Postexposure prophylaxis, exposure to aerosolized spores",
                    "dose_mg_per_kg_per_day": 75,
                    "frequency": 3,
                    "duration_days": 60,
                    "max_mg_per_dose": 1000
                },
                {
                    "title": "Cutaneous, without systemic involvement",
                    "dose_mg_per_kg_per_day": 75,
                    "frequency": 3,
                    "duration_days_range": [7, 10],
                    "max_mg_per_dose": 1000,
                    "note": "ใช้ในกรณี naturally acquired infection"
                },
                {
                    "title": "Systemic, oral step-down therapy",
                    "dose_mg_per_kg_per_day": 75,
                    "frequency": 3,
                    "duration_days": 60,
                    "max_mg_per_dose": 1000,
                    "note": "เป็นส่วนหนึ่งของ combination therapy เพื่อให้ครบ 60 วัน"
                }
            ],
            "H. pylori eradication": [
                {
                    "name": "Standard-dose (weight-based)",
                    "dose_mg_per_kg_per_day": 50,
                    "frequency": 2,
                    "duration_days": 14,
                    "max_mg_per_dose": 1000,
                    "note": "ใช้ร่วมกับยาฆ่าเชื้อชนิดอื่นตาม guideline"
                },
                {
                    "name": "Standard-dose (fixed dosing)",
                    "fixed_dose_by_weight": [
                        {"min_weight": 15, "max_weight": 24.9, "dose_mg": 500},
                        {"min_weight": 25, "max_weight": 34.9, "dose_mg": 750},
                        {"min_weight": 35, "max_weight": 999, "dose_mg": 1000}
                    ],
                    "frequency": 2,
                    "duration_days": 14,
                    "note": "Fixed dosing ตามน้ำหนักช่วง (twice daily × 14 วัน)"
                },
                {
                    "name": "High-dose (fixed dosing)",
                    "fixed_dose_by_weight": [
                        {"min_weight": 15, "max_weight": 24.9, "dose_mg": 750},
                        {"min_weight": 25, "max_weight": 34.9, "dose_mg": 1000},
                        {"min_weight": 35, "max_weight": 999, "dose_mg": 1500}
                    ],
                    "frequency": 2,
                    "duration_days": 14,
                    "note": "ใช้กรณีดื้อ clarithromycin และ metronidazole"
                }
            ],
            "Lyme disease": [
                {
                    "name": "Erythema migrans / Borrelial lymphocytoma",
                    "dose_mg_per_kg_per_day": 50,
                    "frequency": 3,
                    "duration_days": 14,
                    "max_mg_per_dose": 500,
                    "note": "รักษานาน 14 วัน"
                },
                {
                    "name": "Carditis",
                    "dose_mg_per_kg_per_day": 50,
                    "frequency": 3,
                    "duration_days": 21,
                    "max_mg_per_dose": 500,
                    "note": "รักษานาน 14–21 วัน"
                },
                {
                    "name": "Arthritis (initial, recurrent, or refractory)",
                    "dose_mg_per_kg_per_day": 50,
                    "frequency": 3,
                    "duration_days": 28,
                    "max_mg_per_dose": 500,
                    "note": "รักษานาน 28 วัน"
                },
                {
                    "name": "Acrodermatitis chronica atrophicans",
                    "dose_mg_per_kg_per_day": 50,
                    "frequency": 3,
                    "duration_days": 28,
                    "max_mg_per_dose": 500,
                    "note": "รักษานาน 21–28 วัน"
                }
            ],
            "Urinary tract infection": [
                {
                    "sub_indication": "Infants",
                    "dose_mg_per_kg_per_day": 50,
                    "frequency": 2,
                    "duration_days": 7,
                    "note": "📌 แนะนำใช้เฉพาะในกรณีที่เชื้อไวต่อ amoxicillin"
                },
                {
                    "sub_indication": "Infants (severe)",
                    "dose_mg_per_kg_per_day": 100,
                    "frequency": 2,
                    "duration_days": 10,
                    "note": "📌 อาจใช้ในกรณี moderate/severe infection"
                },
                {
                    "sub_indication": "Children and Adolescents",
                    "dose_mg_per_kg_per_day": 50,
                    "frequency": 3,
                    "duration_days": 7,
                    "max_mg_per_dose": 500,
                    "note": "📌 แนะนำระยะเวลา 7–14 วัน หรือ 3–5 วันใน cystitis ที่ไม่ซับซ้อน (≥2 ปี)"
                },
                {
                    "sub_indication": "Children and Adolescents (high dose)",
                    "dose_mg_per_kg_per_day": 100,
                    "frequency": 3,
                    "duration_days": 10,
                    "max_mg_per_dose": 500,
                    "note": "📌 สำหรับ moderate/severe infection ที่ตอบสนองช้า"
                },
                {
                    "sub_indication": "Children (uncomplicated cystitis)",
                    "dose_mg_per_kg_per_day": 30,
                    "frequency": 3,
                    "duration_days": 3,
                    "note": "📌 ใช้ได้ในเด็ก ≥2 ปี ที่มี uncomplicated cystitis"
                }
            ],
            "Rhinosinusitis": [
                {
                    "sub_indication": "Standard-dose regimen (พื้นที่ที่ S. pneumoniae ไวต่อ penicillin)",
                    "dose_mg_per_kg_per_day": 45,
                    "frequency": 2,
                    "duration_days": 10,
                    "note": "📌 สำหรับผู้ป่วยที่ไม่ได้รับยาปฏิชีวนะใน 30 วันที่ผ่านมา และไม่ได้ไปศูนย์ดูแลเด็ก (AAP guideline)"
                },
                {
                    "sub_indication": "High-dose regimen (พื้นที่ที่ S. pneumoniae ดื้อต่อ penicillin ≥10%)",
                    "dose_mg_per_kg_per_day": 80,
                    "frequency": 2,
                    "duration_days": 10,
                    "max_mg_per_dose": 2000,
                    "note": "📌 แนะนำโดย IDSA และใช้ในพื้นที่ที่มีเชื้อดื้อมาก"
                }
            ]
        }
    },
    "Cephalexin": {
        "concentration_mg_per_ml": 125 / 5,
        "bottle_size_ml": 60,
        "indications": {
            "Acute Otitis Media (AOM)": [
            {
                "sub_indication": "Alternative agent",
                "dose_mg_per_kg_per_day": [75, 100],
                "frequency": 4,
                "duration_days": 10,
                "note": "❗ ไม่แนะนำให้ใช้เป็น empiric therapy; ใช้เฉพาะเมื่อทราบเชื้อที่ไวต่อยา"
            }
            ],
            "Pneumonia (community acquired)": [
            {
                "sub_indication": "Step-down therapy for mild infection",
                "dose_mg_per_kg_per_day": [75, 100],
                "frequency": [3, 4],
                "duration_days_range": [5, 10],
                "max_mg_per_day": 4000,
                "note": "📝 ใช้เป็น step-down therapy หลัง IV สำหรับ pneumonia ไม่ซับซ้อน"
            }
            ],
            "SSTI": [
            {
                "sub_indication": "Cellulitis, erysipelas, purulent/fluctuant SSTI",
                "dose_mg_per_kg_per_day": [25, 100],
                "frequency": [3, 4],
                "duration_days_range": [5, 10],
                "max_mg_per_dose": 500,
                "note": "❗ หลีกเลี่ยงการใช้เดี่ยวถ้าสงสัย MRSA; ใช้ dose สูงสุดในกรณีรุนแรงหรือสงสัย MSSA"
            },
            {
                "sub_indication": "Impetigo, ecthyma",
                "dose_mg_per_kg_per_day": [25, 50],
                "frequency": [3, 4],
                "duration_days": 7,
                "max_mg_per_day": 2000
            }
            ],
            "Pharyngitis/Tonsillitis": [
            {
                "sub_indication": "Group A Streptococcus (penicillin allergy)",
                "dose_mg_per_kg_per_day": 40,
                "frequency": 2,
                "duration_days": 10,
                "max_mg_per_dose": 500
            }
            ],
            "UTI": [
            {
                "sub_indication": "Mild to moderate (eg, cystitis)",
                "dose_mg_per_kg_per_day": [25, 50],
                "frequency": [2, 4],
                "duration_days": 5,
                "max_mg_per_dose": 500,
                "note": "📝 ระยะเวลาอาจขยายหากการตอบสนองไม่ดี"
            },
            {
                "sub_indication": "Severe (eg, pyelonephritis)",
                "dose_mg_per_kg_per_day": [50, 100],
                "frequency": [3, 4],
                "duration_days_range": [7, 10],
                "max_mg_per_dose": 1000,
                "note": "📝 ไม่แนะนำให้เกิน 10 วัน; ใช้ตามการตอบสนองทางคลินิก"
            }
            ]
        }
    },
    "Cefdinir": {
        "concentration_mg_per_ml": 125 / 5,
        "bottle_size_ml": 30,
        "indications": {
            "Otitis Media": {"dose_mg_per_kg_per_day": 14, "frequency": 2, "duration_days": 10, "max_mg_per_day": 600},
            "Pharyngitis": {"dose_mg_per_kg_per_day": 14, "frequency": 2, "duration_days": 10, "max_mg_per_day": 600},
            "Rhinosinusitis": {"dose_mg_per_kg_per_day": 14, "frequency": 2, "duration_days": 10, "max_mg_per_day": 600}
        }
    },
    "Cefixime": {
        "concentration_mg_per_ml": 100 / 5,
        "bottle_size_ml": 30,
        "indications": {
            "Febrile Neutropenia": {"dose_mg_per_kg_per_day": 8, "frequency": 1, "duration_days": 7, "max_mg_per_day": 400},
            "Otitis Media": {"dose_mg_per_kg_per_day": 8, "frequency": 1, "duration_days": 7, "max_mg_per_day": 400},
            "Rhinosinusitis": {"dose_mg_per_kg_per_day": 8, "frequency": 1, "duration_days": 7, "max_mg_per_day": 400},
            "Strep Pharyngitis": {"dose_mg_per_kg_per_day": 8, "frequency": 1, "duration_days": 10, "max_mg_per_day": 400},
            "Typhoid Fever": {"dose_mg_per_kg_per_day": 17.5, "frequency": 2, "duration_days": 10, "max_mg_per_day": None},
            "UTI": {"dose_mg_per_kg_per_day": 8, "frequency": 2, "duration_days": 7, "max_mg_per_day": 400}
        }
    },
    "Augmentin": {
        "concentration_mg_per_ml": 600 / 5,
        "bottle_size_ml": 70,
        "indications": {
            "Impetigo": {"dose_mg_per_kg_per_day": 35, "frequency": 2, "duration_days": 7, "max_mg_per_day": 500},
            "Osteoarticular Infection": {  "dose_mg_per_kg_per_day": 120,"frequency": 3, "duration_days": 21,"max_mg_per_day": 1000 },
            "Otitis Media": {"dose_mg_per_kg_per_day": 85,"frequency": 2, "duration_days": 10, "max_mg_per_day": 2000 },
            "Pneumonia": { "dose_mg_per_kg_per_day": 90,"frequency": 2, "duration_days": 7, "max_mg_per_day": 2000 },
            "Rhinosinusitis": {"dose_mg_per_kg_per_day": 90,"frequency": 2,"duration_days": 10,"max_mg_per_day": 2000 },
            "Strep Carriage": { "dose_mg_per_kg_per_day": 40, "frequency": 3, "duration_days": 10,"max_mg_per_day": 2000 },
            "UTI": { "dose_mg_per_kg_per_day": 35, "frequency": 2, "duration_days": 7, "max_mg_per_day": 1750 }
        }
    },
    "Azithromycin": {
        "concentration_mg_per_ml": 200 / 5,
        "bottle_size_ml": 15,
        "indications": {
            "Pertussis": [
                {"day_range": "Day 1", "dose_mg_per_kg_per_day": 10, "frequency": 1, "duration_days": 1, "max_mg_per_day": 500},
                {"day_range": "Day 2–5", "dose_mg_per_kg_per_day": 5, "frequency": 1, "duration_days": 4, "max_mg_per_day": 250}
            ],
            "Pneumonia (Atypical)": [
                {"day_range": "Day 1", "dose_mg_per_kg_per_day": 10, "frequency": 1, "duration_days": 1, "max_mg_per_day": 500},
                {"day_range": "Day 2–5", "dose_mg_per_kg_per_day": 5, "frequency": 1, "duration_days": 4, "max_mg_per_day": 250}
            ],
            "Strep Pharyngitis": {
                "dose_mg_per_kg_per_day": 12, "frequency": 1, "duration_days": 5, "max_mg_per_dose": 500
            },
            "Typhoid Fever": {
                "dose_mg_per_kg_per_day": 15, "frequency": 1, "duration_days": 7, "max_mg_per_dose": 1000
            },
            "UTI (Off-label)": {
                "dose_mg_per_kg_per_day": 10, "frequency": 1, "duration_days": 3, "max_mg_per_dose": 500
            },
            "Rhinosinusitis": {
                "dose_mg_per_kg_per_day": 10, "frequency": 1, "duration_days": 3, "max_mg_per_dose": 500
            },
            "Chlamydia": {
                "dose_mg_per_kg_per_day": 20, "frequency": 1, "duration_days": 1, "max_mg_per_dose": 1000
            },
            "Diarrhea (Campylobacter)": {
                "dose_mg_per_kg_per_day": 10, "frequency": 1, "duration_days": 3, "max_mg_per_dose": 500
            },
            "Diarrhea (Shigella)": [
                {"day_range": "Day 1", "dose_mg_per_kg_per_day": 12, "frequency": 1, "duration_days": 1, "max_mg_per_day": 500},
                {"day_range": "Day 2–5", "dose_mg_per_kg_per_day": 5, "frequency": 1, "duration_days": 4, "max_mg_per_day": 250}
            ],
            "Cholera": {
                "dose_mg_per_kg_per_day": 20, "frequency": 1, "duration_days": 1, "max_mg_per_dose": 1000
            },
            "Babesiosis": [
                {"day_range": "Day 1", "dose_mg_per_kg_per_day": 10, "frequency": 1, "duration_days": 1, "max_mg_per_day": 500},
                {"day_range": "Day 2–5", "dose_mg_per_kg_per_day": 5, "frequency": 1, "duration_days": 4, "max_mg_per_day": 250}
            ],
            "Cat Scratch Disease": [
                {"day_range": "Day 1", "dose_mg_per_kg_per_day": 10, "frequency": 1, "duration_days": 1, "max_mg_per_day": 500},
                {"day_range": "Day 2–5", "dose_mg_per_kg_per_day": 5, "frequency": 1, "duration_days": 4, "max_mg_per_day": 250}
            ],
            "MAC (Mycobacterium avium, prophylaxis)": {
                "dose_mg_per_kg_per_day": 20, "frequency": 1, "duration_days": 7, "max_mg_per_dose": 1200
            },
            "NTM Pulmonary Infection": {
                "dose_mg_per_kg_per_day": 10, "frequency": 1, "duration_days": 14, "max_mg_per_dose": 500
            },
            "Cystic Fibrosis (maintenance)": {
                "dose_mg_per_kg_per_day": 10, "frequency": 3, "duration_days": 14, "max_mg_per_dose": 500
            },
            "Asthma (Adjunct)": {
                "dose_mg_per_kg_per_day": 10, "frequency": 3, "duration_days": 14, "max_mg_per_dose": 500
            },
            "Other": "INDICATION_OTHERS"
        },
        "common_indications": ["Pneumonia (Atypical)", "Strep Pharyngitis","Rhinosinusitis","Chlamydia" ]
    }
}


logging.basicConfig(
    level=logging.INFO,  # เปลี่ยนเป็น DEBUG ถ้าต้องการ log ละเอียด
    format='[%(asctime)s] %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()  # พิมพ์ log ไปยัง stdout (เช่น Render, Cloud Run จะเห็น)
    ]
)

app = Flask(__name__)

LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET")

if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_CHANNEL_SECRET:
    raise ValueError("Missing LINE_CHANNEL_ACCESS_TOKEN or LINE_CHANNEL_SECRET")

configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
api_client = ApiClient(configuration)
messaging_api = MessagingApi(api_client)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

user_drug_selection = {}
user_sessions = {}
user_ages = {}


SPECIAL_DRUGS = {
    "Paracetamol": {
    "concentration_mg_per_ml": 120 / 5,
    "bottle_size_ml": 60,
    "indications": {
        "Fever": [
            {
                "min_age_years": 0,
                "max_age_years": 6,
                "dose_mg_per_kg_per_day": 60,
                "frequency": 4,
                "duration_days": 3,
                "max_mg_per_dose": 250
            },
            {
                "min_age_years": 6,
                "max_age_years": 18,
                "dose_mg_per_kg_per_day": 60,
                "frequency": 4,
                "duration_days": 3,
                "max_mg_per_dose": 500
            }
        ]
    },
    "common_indications": ["Fever"]
    },
    "Cetirizine": {
    "concentration_mg_per_ml": 5 / 5,
    "bottle_size_ml": 60,
    "indications": {
            "Allergic rhinitis, perennial": {
                "6_to_23_months": {
                    "initial_dose_mg": 2.5,
                    "frequency": 1,
                    "max_frequency": 1,
                    "max_mg_per_day": 2.5
                },
                "2_to_5_years": {
                    "initial_dose_mg": 2.5,
                    "frequency": 1,
                    "options": [
                        {"dose_mg": 2.5, "frequency": 2},
                        {"dose_mg": 5, "frequency": 1}
                    ],
                    "max_mg_per_day": 5
                },
                "above_5": {
                    "dose_mg_range": [5, 10],
                    "frequency": 1,
                    "max_mg_per_day": 10
                }
            },
            "Allergic symptoms, hay fever": {
                "2_to_5_years": {
                    "initial_dose_mg": 2.5,
                    "frequency": 1,
                    "options": [
                        {"dose_mg": 2.5, "frequency": 2},
                        {"dose_mg": 5, "frequency": 1}
                    ],
                    "max_mg_per_day": 5
                },
                "above_5": {
                    "dose_mg_range": [5, 10],
                    "frequency": 1,
                    "max_mg_per_day": 10
                }
            },
            "Anaphylaxis (adjunctive only)": {
                "6_to_23_months": {
                    "initial_dose_mg": 2.5,
                    "frequency": 1,
                    "max_mg_per_day": 2.5
                },
                "2_to_5_years": {
                    "dose_mg_range": [2.5, 5],
                    "frequency": 1,
                    "max_mg_per_day": 5
                },
                "above_5": {
                    "dose_mg_range": [5, 10],
                    "frequency": 1,
                    "max_mg_per_day": 10
                }
            },
            "Urticaria, acute": {
                "6_to_23_months": {
                    "initial_dose_mg": 2.5,
                    "frequency": 1,
                    "max_mg_per_day": 2.5
                },
                "2_to_5_years": {
                    "dose_mg_range": [2.5, 5],
                    "frequency": 1,
                    "max_mg_per_day": 5
                },
                "above_5": {
                    "dose_mg_range": [5, 10],
                    "frequency": 1,
                    "max_mg_per_day": 10
                }
            },
            "Urticaria, chronic spontaneous": {
                "6_to_23_months": {
                    "initial_dose_mg": 2.5,
                    "frequency": 1,
                    "max_frequency": 2,
                    "max_mg_per_day": 5
                },
                "2_to_5_years": {
                    "initial_dose_mg": 2.5,
                    "frequency": 1,
                    "options": [
                        {"dose_mg": 2.5, "frequency": 2},
                        {"dose_mg": 5, "frequency": 1}
                    ],
                    "max_mg_per_day": 5
                },
                "6_to_11_years": {
                    "dose_mg": 5,
                    "frequency_options": [1, 2],
                    "max_mg_per_day": 10
                },
                "above_or_equal_12": {
                    "dose_mg": 10,
                    "frequency": 1,
                    "max_mg_per_day": 10
                }
            }
        },
        "common_indications": [
        "Allergic rhinitis, perennial",
        "Allergic symptoms, hay fever",
        "Anaphylaxis (adjunctive only)",
        "Urticaria, acute",
        "Urticaria, chronic spontaneous"
        ]
    },
    "Hydroxyzine": {
        "concentration_mg_per_ml": 10 / 5 ,
        "bottle_size_ml": 60,
        "indications": {
        "Anxiety": {
            "under_6": {
            "dose_mg": 12.5,
            "frequency": 4,
            "max_mg_per_dose": 12.5
            },
            "above_or_equal_6": {
            "dose_mg_range": [12.5, 25],
            "frequency": 4,
            "max_mg_per_dose": 25
            }
        },
        "Pruritus (age-based)": {
            "under_6": {
            "dose_mg": 12.5,
            "frequency": [3, 4],
            "max_mg_per_dose": 12.5
            },
            "above_or_equal_6": {
            "dose_mg_range": [12.5, 25],
            "frequency": [3, 4],
            "max_mg_per_dose": 25
            }
        },
        "Pruritus (weight_based)": {
            "≤40kg": {
                "dose_mg_per_kg_per_day": 2,
                "frequency": [6, 8],
                "max_mg_per_dose": 25
            },
            ">40kg": {
                "dose_mg_range": [25, 50],
                "frequency": [1, 2],
                "max_mg_per_dose": 50
            }
        },
        "Pruritus from opioid": {
            "all_ages": {
            "dose_mg_per_kg_per_dose": 0.5,
            "frequency": 6,
            "max_mg_per_dose": 50
            }
        },
        "Sedation": {
            "all_ages": {
            "dose_mg_per_kg": 0.6,
            "max_mg_per_dose": 100
            }
        }
        },
        "common_indications": [
        "Anxiety",
        "Pruritus (age-based)",
        "Pruritus (weight_based)",
        "Pruritus from opioid",
        "Sedation"
        ]
    },
    "Ferrous drop": {
        "concentration_mg_per_ml": 15 / 0.6 ,
        "bottle_size_ml": 15,
        "indications": {
        "Iron deficiency, treatment": {
            "all_ages": {
            "initial_dose_mg_per_kg_per_day": 3,
            "max_dose_range_mg_per_day": [60, 120],
            "usual_max_mg_per_day": 150,
            "absolute_max_mg_per_day": 200,
            "frequency": [1, 3],
            "note": "ให้ครั้งเดียว หรือแบ่งวันละ 1–3 ครั้งได้; การให้วันเว้นวันอาจช่วยดูดซึมดีขึ้น"
            }
        }
        },
        "common_indications": [
        "Iron deficiency, treatment"
        ]
    }
    }

@app.route('/')
def home():
    return 'LINE Bot is running!'

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    except Exception as e:
        logging.info(f"❌ Exception occurred: {e}")
        abort(400)
    return 'OK'

def send_drug_selection(event):
    carousel1 = CarouselTemplate(columns=[
        CarouselColumn(title='Amoxicillin', text='250 mg/5 ml', actions=[MessageAction(label='เลือก Amoxicillin', text='เลือกยา: Amoxicillin')]),
        CarouselColumn(title='Cephalexin', text='125 mg/5 ml', actions=[MessageAction(label='เลือก Cephalexin', text='เลือกยา: Cephalexin')]),
        CarouselColumn(title='Cefdinir', text='125 mg/5 ml', actions=[MessageAction(label='เลือก Cefdinir', text='เลือกยา: Cefdinir')]),
        CarouselColumn(title='Cefixime', text='100 mg/5 ml', actions=[MessageAction(label='เลือก Cefixime', text='เลือกยา: Cefixime')]),
        CarouselColumn(title='Augmentin', text='600 mg/5 ml', actions=[MessageAction(label='เลือก Augmentin', text='เลือกยา: Augmentin')]),
    ])
    carousel2 = CarouselTemplate(columns=[
        CarouselColumn(title='Azithromycin', text='200 mg/5 ml', actions=[MessageAction(label='เลือก Azithromycin', text='เลือกยา: Azithromycin')]),
        CarouselColumn(title='Paracetamol', text='10–15 mg/kg/dose', actions=[MessageAction(label='เลือก Paracetamol', text='เลือกยา: Paracetamol')]),
        CarouselColumn(title='Cetirizine', text='0.25 mg/kg/day', actions=[MessageAction(label='เลือก Cetirizine', text='เลือกยา: Cetirizine')]),
        CarouselColumn(title='Hydroxyzine', text='10 mg/5 ml', actions=[MessageAction(label='เลือก Hydroxyzine', text='เลือกยา: Hydroxyzine')]),
        CarouselColumn(title='Ferrous drop', text='15 mg/0.6 ml', actions=[MessageAction(label='เลือก Ferrous drop', text='เลือกยา: Ferrous drop')])
    ])
    messaging_api.reply_message(
    ReplyMessageRequest(
        reply_token=event.reply_token,
        messages=[
            TemplateMessage(alt_text="เลือกยากลุ่มแรก", template=carousel1),
            TemplateMessage(alt_text="เลือกยากลุ่มเพิ่มเติม", template=carousel2)
        ]
    ))
    return

def send_indication_carousel(event, drug_name, show_all=False):
    drug_info = DRUG_DATABASE.get(drug_name)
    if not drug_info or "indications" not in drug_info:
        messaging_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=f"ไม่พบข้อมูลสำหรับยา {drug_name}")]
            )
        )
        return

    indications = drug_info["indications"]
    common = drug_info.get("common_indications", [])

    if not show_all and common:
        names_to_show = common + ["Indication อื่นๆ"]
    else:
        names_to_show = [name for name in indications.keys() if name not in common and name != "Other"]

    columns = []

    for name in names_to_show:
        label = "เลือก"
        title = name[:40] if len(name) > 40 else name

        if name != "Indication อื่นๆ":
            indication_info = indications[name]
            if isinstance(indication_info, list):
                text = f"{indication_info[0]['dose_mg_per_kg_per_day']} mg/kg/day"
            else:
                text = f"{indication_info['dose_mg_per_kg_per_day']} mg/kg/day"
            action_text = f"Indication: {name}"
        else:
            text = "ดูข้อบ่งใช้อื่นทั้งหมด"
            action_text = f"MoreIndication: {drug_name}"

        actions = [MessageAction(label=label, text=action_text)]
        columns.append(CarouselColumn(title=title, text=text, actions=actions))

    carousel_chunks = [columns[i:i + 5] for i in range(0, len(columns), 5)]
    messages = []

    for chunk in carousel_chunks:
        try:
            messages.append(
                TemplateMessage(
                    alt_text=f"ข้อบ่งใช้ {drug_name}",
                    template=CarouselTemplate(columns=chunk)
                )
            )
        except Exception as e:
            logging.info(f"⚠️ ผิดพลาดตอนสร้าง TemplateMessage: {e}")

    logging.info(f"📤 ส่ง carousel ทั้งหมด: {len(messages)} ชุด")
    try:
        messaging_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=messages
            )
        )
        return
    except Exception as e:
        logging.info(f"❌ ผิดพลาดตอนส่งข้อความ: {e}")


def calculate_warfarin(inr, twd, bleeding, supplement=None):
    if bleeding == "yes":
        return "🚨 มี major bleeding → หยุด Warfarin, ให้ Vitamin K1 10 mg IV"

    warning = ""
    if supplement:
        herb_map = {
            "กระเทียม": "garlic", "ใบแปะก๊วย": "ginkgo", "โสม": "ginseng",
            "ขมิ้น": "turmeric", "น้ำมันปลา": "fish oil",
            "dong quai": "dong quai", "cranberry": "cranberry"
        }
        high_risk = list(herb_map.keys())
        matched = [name for name in high_risk if name in supplement]
        if matched:
            herbs = ", ".join(matched)
            warning = f"\n⚠️ พบว่าสมุนไพร/อาหารเสริมที่อาจมีผลต่อ INR ได้แก่: {herbs}\nโปรดพิจารณาความเสี่ยงต่อการเปลี่ยนแปลง INR อย่างใกล้ชิด"
        else:
            warning = "\n⚠️ มีการใช้อาหารเสริมหรือสมุนไพร → พิจารณาความเสี่ยงต่อการเปลี่ยนแปลง INR"

    followup_text = get_followup_text(inr)

    if inr < 1.5:
        result = f"🔹 INR < 1.5 → เพิ่มขนาดยา 10–20%\nขนาดยาใหม่: {twd * 1.1:.1f} – {twd * 1.2:.1f} mg/สัปดาห์"
    elif 1.5 <= inr <= 1.9:
        result = f"🔹 INR 1.5–1.9 → เพิ่มขนาดยา 5–10%\nขนาดยาใหม่: {twd * 1.05:.1f} – {twd * 1.10:.1f} mg/สัปดาห์"
    elif 2.0 <= inr <= 3.0:
        result = "✅ INR 2.0–3.0 → คงขนาดยาเดิม"
    elif 3.1 <= inr <= 3.9:
        result = f"🔹 INR 3.1–3.9 → ลดขนาดยา 5–10%\nขนาดยาใหม่: {twd * 0.9:.1f} – {twd * 0.95:.1f} mg/สัปดาห์"
    elif 4.0 <= inr <= 4.9:
        result = f"⚠️ INR 4.0–4.9 → หยุดยา 1 วัน และลดขนาดยา 10%\nขนาดยาใหม่: {twd * 0.9:.1f} mg/สัปดาห์"
    elif 5.0 <= inr <= 8.9:
        result = "⚠️ INR 5.0–8.9 → หยุดยา 1–2 วัน และพิจารณาให้ Vitamin K1 1 mg"
    else:
        result = "🚨 INR ≥ 9.0 → หยุดยา และพิจารณาให้ Vitamin K1 5–10 mg"

    return f"{result}{warning}\n\n{followup_text}"

def get_inr_followup(inr):
    if inr < 1.5: return 7
    elif inr <= 1.9: return 14
    elif inr <= 3.0: return 56
    elif inr <= 3.9: return 14
    elif inr <= 6.0: return 7
    elif inr <= 8.9: return 5
    elif inr > 9.0: return 2
    return None

def get_followup_text(inr):
    days = get_inr_followup(inr)
    if days:
        date = (datetime.now() + timedelta(days=days)).strftime("%-d %B %Y")
        return f"📅 คำแนะนำ: ควรตรวจ INR ภายใน {days} วัน\n📌 วันที่ควรตรวจ: {date}"
    else:
        return ""

# --------------------------
# ส่ง flex เลือกสมุนไพร
# --------------------------
def send_supplement_flex(event):
    flex_bubble = {
  "type": "bubble",
  "size": "mega",
  "header": {
    "type": "box",
    "layout": "vertical",
    "contents": [
      {
        "type": "text",
        "text": "🌿 สมุนไพร/อาหารเสริม",
        "weight": "bold",
        "size": "lg"
      }
    ]
  },
  "body": {
    "type": "box",
    "layout": "vertical",
    "spacing": "md",
    "contents": [
      {
        "type": "text",
        "text": "ผู้ป่วยใช้สิ่งใดบ้าง?",
        "wrap": true,
        "size": "md"
      },
      {
        "type": "box",
        "layout": "vertical",
        "spacing": "sm",
        "contents": [
          {
            "type": "button",
            "style": "primary",
            "height": "sm",
            "action": {
              "type": "message",
              "label": "ไม่ได้ใช้",
              "text": "ไม่ได้ใช้"
            },
            "color": "#84C1FF"
          },
          {
            "type": "button",
            "style": "primary",
            "height": "sm",
            "action": {
              "type": "message",
              "label": "กระเทียม",
              "text": "กระเทียม"
            },
            "color": "#AEC6CF"
          },
          {
            "type": "button",
            "style": "primary",
            "height": "sm",
            "action": {
              "type": "message",
              "label": "ใบแปะก๊วย",
              "text": "ใบแปะก๊วย"
            },
            "color": "#AEC6CF"
          },
          {
            "type": "button",
            "style": "primary",
            "height": "sm",
            "action": {
              "type": "message",
              "label": "โสม",
              "text": "โสม"
            },
            "color": "#AEC6CF"
          },
          {
            "type": "button",
            "style": "primary",
            "height": "sm",
            "action": {
              "type": "message",
              "label": "ขมิ้น",
              "text": "ขมิ้น"
            },
            "color": "#AEC6CF"
          },
          {
            "type": "button",
            "style": "primary",
            "height": "sm",
            "action": {
              "type": "message",
              "label": "น้ำมันปลา",
              "text": "น้ำมันปลา"
            },
            "color": "#AEC6CF"
          },
          {
            "type": "button",
            "style": "primary",
            "height": "sm",
            "action": {
              "type": "message",
              "label": "ใช้หลายชนิด",
              "text": "ใช้หลายชนิด"
            },
            "color": "#AEC6CF"
          },
          {
            "type": "button",
            "style": "primary",
            "height": "sm",
            "action": {
              "type": "message",
              "label": "สมุนไพร/อาหารเสริมชนิดอื่นๆ",
              "text": "สมุนไพร/อาหารเสริมชนิดอื่นๆ"
            },
            "color": "#AEC6CF"
          }
        ]
      }
    ]
  },
  "styles": {
    "header": {
      "backgroundColor": "#D0E6FF"
    },
    "body": {
      "backgroundColor": "#FFFFFF"
    }
  }
}

    flex_message = FlexMessage(
        alt_text="เลือกสมุนไพร/อาหารเสริม",
        contents=flex_bubble
    )

    messaging_api.reply_message(
        ReplyMessageRequest(
            reply_token=event.reply_token,
            messages=[flex_message]
        )
    )

def calculate_dose(drug, indication, weight):
    drug_info = DRUG_DATABASE.get(drug)
    if not drug_info:
        return f"❌ ไม่พบข้อมูลยา {drug}"

    indication_info = drug_info["indications"].get(indication)
    if not indication_info:
        return f"❌ ไม่พบ indication {indication} ใน {drug}"

    conc = drug_info["concentration_mg_per_ml"]
    bottle_size = drug_info["bottle_size_ml"]
    total_ml = 0
    reply_lines = [f"{drug} - {indication} (น้ำหนัก {weight} kg):"]

    # ✅ รองรับกรณี indication เป็น dict ซ้อน (sub-indications)
    if isinstance(indication_info, dict) and all(isinstance(v, dict) for v in indication_info.values()):
        for sub_ind, sub_info in indication_info.items():
            dose_per_kg = sub_info["dose_mg_per_kg_per_day"]
            freqs = sub_info["frequency"] if isinstance(sub_info["frequency"], list) else [sub_info["frequency"]]
            days = sub_info["duration_days"]
            max_mg_day = sub_info.get("max_mg_per_day")
            max_mg_per_dose = sub_info.get("max_mg_per_dose")
            note = sub_info.get("note")

            if isinstance(dose_per_kg, list):
                min_dose, max_dose = dose_per_kg
                min_total_mg_day = weight * min_dose
                max_total_mg_day = weight * max_dose

                if max_mg_day:
                    min_total_mg_day = min(min_total_mg_day, max_mg_day)
                    max_total_mg_day = min(max_total_mg_day, max_mg_day)

                ml_per_day_min = min_total_mg_day / conc
                ml_per_day_max = max_total_mg_day / conc
                ml_total = ml_per_day_max * days
                total_ml += ml_total
                dose_min = ml_per_day_min / max(freqs)
                dose_max = ml_per_day_max / min(freqs)
                min_freq = min(freqs)
                max_freq = max(freqs)
                if min_freq == max_freq:
                    freq_text = f"{min_freq} ครั้ง"
                else:
                    freq_text = f"{min_freq} – {max_freq} ครั้ง"
                reply_lines.append(
                    f"📌 {sub_ind}: {min_dose} – {max_dose} mg/kg/day → {min_total_mg_day:.0f} – {max_total_mg_day:.0f} mg/day ≈ "
                    f"{ml_per_day_min:.1f} – {ml_per_day_max:.1f} ml/day, แบ่งวันละ {freq_text} × {days} วัน "
                )
            else:
                total_mg_day = weight * dose_per_kg
                if max_mg_day:
                    total_mg_day = min(total_mg_day, max_mg_day)
                ml_per_day = total_mg_day / conc
                ml_total = ml_per_day * days
                total_ml += ml_total

                if len(freqs) == 1:
                    freq = freqs[0]
                    ml_per_dose = ml_per_day / freq
                    if max_mg_per_dose:
                        ml_per_dose = min(ml_per_dose, max_mg_per_dose / conc)
                    reply_lines.append(
                        f"📌 {sub_ind}: {dose_per_kg} mg/kg/day → {total_mg_day:.0f} mg/day ≈ {ml_per_day:.1f} ml/day, "
                        f"ครั้งละ ~{ml_per_dose:.1f} ml × {freq} ครั้ง/วัน × {days} วัน"
                    )
                else:
                    min_freq = min(freqs)
                    max_freq = max(freqs)
                    if min_freq == max_freq:
                        freq_text = f"{min_freq} ครั้ง"
                    else:
                        freq_text = f"{min_freq} – {max_freq} ครั้ง"
                    reply_lines.append(
                        f"📌 {sub_ind}: {dose_per_kg} mg/kg/day → {total_mg_day:.0f} mg/day ≈ {ml_per_day:.1f} ml/day, "
                        f"แบ่งวันละ {freq_text} × {days} วัน (ครั้งละ ~{ml_per_day / max_freq:.1f} – {ml_per_day / min_freq:.1f} ml)"
                    )

            if note:
                reply_lines.append(f"📝 หมายเหตุ: {note}")

    elif isinstance(indication_info, list):
        for phase in indication_info:
            title = get_indication_title(phase)
            if title:
                reply_lines.append(f"\n🔹 {title}")

            dose_per_kg = phase["dose_mg_per_kg_per_day"]
            freqs = phase["frequency"] if isinstance(phase["frequency"], list) else [phase["frequency"]]
            days = phase.get("duration_days")
            days = phase.get("duration_days")
            days_range = phase.get("duration_days_range")
            if not days and days_range:
                min_days, max_days = days_range
                days = max_days
            else:
                min_days = max_days = days

            max_mg_day = phase.get("max_mg_per_day")
            max_mg_per_dose = phase.get("max_mg_per_dose")

            if isinstance(dose_per_kg, list):
                min_dose, max_dose = dose_per_kg
                min_total_mg_day = weight * min_dose
                max_total_mg_day = weight * max_dose
                if max_mg_day:
                    min_total_mg_day = min(min_total_mg_day, max_mg_day)
                    max_total_mg_day = min(max_total_mg_day, max_mg_day)
                ml_per_day_min = min_total_mg_day / conc
                ml_per_day_max = max_total_mg_day / conc
                ml_phase = ml_per_day_max * days
                raw_bottles = ml_phase / bottle_size
                bottles = math.ceil(raw_bottles)
                dose_min = ml_per_day_min / max(freqs)
                dose_max = ml_per_day_max / min(freqs)
                min_freq = min(freqs)
                max_freq = max(freqs)
                if min_freq == max_freq:
                    freq_text = f"{min_freq} ครั้ง"
                else:
                    freq_text = f"{min_freq} – {max_freq} ครั้ง"
                reply_lines.append(
                    f"📆 {phase.get('day_range', '')}: {min_dose} – {max_dose} mg/kg/day → {min_total_mg_day:.0f} – {max_total_mg_day:.0f} mg/day ≈ "
                    f"{ml_per_day_min:.1f} – {ml_per_day_max:.1f} ml/day, แบ่งวันละ {freq_text} × {days} วัน "
                    f"(ครั้งละ ~{dose_min:.1f} – {dose_max:.1f} ml)"
                    
                )
                reply_lines.append(
                    f"รวมทั้งหมด {ml_phase:.1f} ml → ต้องใช้ ~{raw_bottles:.1f} ขวด → จ่าย {bottles} ขวด ({bottle_size} ml)"
                )
            else:
                total_mg_day = weight * dose_per_kg
                if max_mg_day:
                    total_mg_day = min(total_mg_day, max_mg_day)
                ml_per_day = total_mg_day / conc
                ml_phase = ml_per_day * days
                bottles = math.ceil(ml_phase / bottle_size)

                if len(freqs) == 1:
                    freq = freqs[0]
                    ml_per_dose = ml_per_day / freq
                    if max_mg_per_dose:
                        ml_per_dose = min(ml_per_dose, max_mg_per_dose / conc)
                    reply_lines.append(
                        f"📆 {phase.get('day_range', '')}: {dose_per_kg} mg/kg/day → {total_mg_day:.0f} mg/day ≈ {ml_per_day:.1f} ml/day, "
                        f"ครั้งละ ~{ml_per_dose:.1f} ml × {freq} ครั้ง/วัน × {days} วัน"
                    )
                else:
                    min_freq = min(freqs)
                    max_freq = max(freqs)
                    freq_text = f"{min_freq} ครั้ง" if min_freq == max_freq else f"{min_freq} – {max_freq} ครั้ง"
                    dose_min = ml_per_day / max_freq
                    dose_max = ml_per_day / min_freq
                    reply_lines.append(
                        f"📆 {phase.get('day_range', '')}: {dose_per_kg} mg/kg/day → {total_mg_day:.0f} mg/day ≈ {ml_per_day:.1f} ml/day, "
                        f"แบ่งวันละ {freq_text} × {days} วัน (ครั้งละ ~{dose_min:.1f} – {dose_max:.1f} ml)"
                    )
                    note = phase.get("note")
                    if note:
                        reply_lines.append(f"📝 หมายเหตุ: {note}")

                reply_lines.append(
                    f"รวมทั้งหมด {ml_phase:.1f} ml → จ่าย {bottles} ขวด ({bottle_size} ml)"
                )
                
                

    # ✅ กรณี indication เป็น dict ธรรมดา
    else:
        dose_per_kg = indication_info["dose_mg_per_kg_per_day"]
        freqs = indication_info["frequency"] if isinstance(indication_info["frequency"], list) else [indication_info["frequency"]]
        days = indication_info["duration_days"]
        max_mg_day = indication_info.get("max_mg_per_day")

        if isinstance(dose_per_kg, list):
            min_dose, max_dose = dose_per_kg
            min_total_mg_day = weight * min_dose
            max_total_mg_day = weight * max_dose

            if max_mg_day:
                min_total_mg_day = min(min_total_mg_day, max_mg_day)
                max_total_mg_day = min(max_total_mg_day, max_mg_day)

            ml_per_day_min = min_total_mg_day / conc
            ml_per_day_max = max_total_mg_day / conc
            total_ml = ml_per_day_max * days

            min_freq = min(freqs)
            max_freq = max(freqs)
            if min_freq == max_freq:
                freq_text = f"{min_freq} ครั้ง"
            else:
                freq_text = f"{min_freq} – {max_freq} ครั้ง"
            dose_min = min(ml_per_day_min / max_freq, ml_per_day_max / max_freq)
            dose_max = max(ml_per_day_min / min_freq, ml_per_day_max / min_freq)    
            reply_lines.append(
                f"ขนาดยา: {min_dose} – {max_dose} mg/kg/day → {min_total_mg_day:.0f} – {max_total_mg_day:.0f} mg/day ≈ "
                f"{ml_per_day_min:.1f} – {ml_per_day_max:.1f} ml/day, แบ่งวันละ {freq_text} × {days} วัน (ครั้งละ ~{dose_min:.1f} – {dose_max:.1f} ml)"
            )
        else:
            total_mg_day = weight * dose_per_kg
            if max_mg_day:
                total_mg_day = min(total_mg_day, max_mg_day)

            ml_per_day = total_mg_day / conc
            total_ml = ml_per_day * days

            if len(freqs) == 1:
                freq = freqs[0]
                ml_per_dose = ml_per_day / freq
                if "max_mg_per_dose" in indication_info:
                    ml_per_dose = min(ml_per_dose, indication_info["max_mg_per_dose"] / conc)
                reply_lines.append(
                    f"ขนาดยา: {dose_per_kg} mg/kg/day → {total_mg_day:.0f} mg/day ≈ {ml_per_day:.1f} ml/day, "
                    f"ครั้งละ ~{ml_per_dose:.1f} ml × {freq} ครั้ง/วัน × {days} วัน"
                )
            else:
                min_freq = min(freqs)
                max_freq = max(freqs)
                if min_freq == max_freq:
                    freq_text = f"{min_freq} ครั้ง"
                else:
                    freq_text = f"{min_freq} – {max_freq} ครั้ง"
                reply_lines.append(
                    f"ขนาดยา: {dose_per_kg} mg/kg/day → {total_mg_day:.0f} mg/day ≈ {ml_per_day:.1f} ml/day, "
                    f"แบ่งวันละ {freq_text} × {days} วัน (ครั้งละ ~{ml_per_day / max_freq:.1f} – {ml_per_day / min_freq:.1f} ml)"
                )

        note = indication_info.get("note")
        if note:
            reply_lines.append(f"\n📝 หมายเหตุ: {note}")
    return "\n".join(reply_lines)

def calculate_special_drug(user_id, drug, weight, age):
    info = SPECIAL_DRUGS[drug]
    indication = user_drug_selection.get(user_id, {}).get("indication")

    if drug == "Hydroxyzine" and indication == "Pruritus (weight_based)":
        data = info["indications"][indication]
        if weight <= 40:
            profile = data["\u226440kg"]  # ≤ = less than or equal to
            dose_per_kg = profile["dose_mg_per_kg_per_day"]
            freqs = profile["frequency"] if isinstance(profile["frequency"], list) else [profile["frequency"]]
            max_dose = profile["max_mg_per_dose"]

            total_mg_day = weight * dose_per_kg
            reply_lines = [f"{drug} - {indication} (\u226440kg):"]
            for freq in freqs:
                dose_per_time = min(total_mg_day / freq, max_dose)
                reply_lines.append(f"💊 {total_mg_day:.1f} mg/day → {freq} ครั้ง/วัน → ครั้งละ ~{dose_per_time:.1f} mg")
            return "\n".join(reply_lines)

        else:
            profile = data[">40kg"]
            dose_range = profile["dose_mg_range"]
            freqs = profile["frequency"] if isinstance(profile["frequency"], list) else [profile["frequency"]]
            max_dose = profile["max_mg_per_dose"]

            reply_lines = [f"{drug} - {indication} (>40kg):"]
            for freq in freqs:
                for dose in dose_range:
                    dose_per_time = min(dose, max_dose)
                    reply_lines.append(f"💊 {dose_per_time:.1f} mg × {freq} ครั้ง/วัน")
            return "\n".join(reply_lines)
    
    if drug == "Cetirizine":
        indication_info = info["indications"].get(indication)
        if not indication_info:
            return f"❌ ไม่พบข้อบ่งใช้ {indication}"

        possible_groups = indication_info.keys()
        age_group = None

        if 0.5 <= age < 2:
            if "6_to_11_months" in possible_groups and age < 1:
                age_group = "6_to_11_months"
            elif "12_to_23_months" in possible_groups and 1 <= age < 2:
                age_group = "12_to_23_months"
            elif "6_to_23_months" in possible_groups:
                age_group = "6_to_23_months"
        elif 2 <= age <= 5 and "2_to_5_years" in possible_groups:
            age_group = "2_to_5_years"
        elif age > 5:
            if "above_5" in possible_groups:
                age_group = "above_5"
            elif "6_to_11_years" in possible_groups and age <= 11:
                age_group = "6_to_11_years"
            elif "above_or_equal_12" in possible_groups and age >= 12:
                age_group = "above_or_equal_12"

        if not age_group:
            return f"❌ ไม่พบข้อมูลกลุ่มอายุที่เหมาะสม (อายุ {age} ปี)"

        group_data = indication_info.get(age_group)
        if not group_data:
            return f"❌ ไม่พบข้อมูลในกลุ่มอายุ '{age_group}'"

        concentration = info.get("concentration_mg_per_ml")
        lines = [f"{drug} - {indication} (อายุ {age} ปี):"]

        # 🔍 ตรวจและแสดงขนาดยา
        if "dose_mg" in group_data and "frequency" in group_data:
            dose = group_data["dose_mg"]
            freq = group_data["frequency"]
            lines.append(f"💊 ขนาดยา: {dose} mg × {freq} ครั้ง/วัน")
            if concentration:
                ml = round(dose / concentration, 2)
                total_ml = round(ml * freq, 2)
                lines.append(f"🧪 เทียบเป็น: {ml} ml × {freq} = {total_ml} ml/วัน")
        elif "initial_dose_mg" in group_data:
            init = group_data["initial_dose_mg"]
            freq = group_data["frequency"]
            lines.append(f"💊 เริ่มต้น {init} mg × {freq} ครั้ง/วัน")
            if concentration:
                ml = round(init / concentration, 2)
                total_ml = round(ml * freq, 2)
                lines.append(f"🧪 เทียบเป็น: {ml} ml × {freq} = {total_ml} ml/วัน")
            for opt in group_data.get("options", []):
                dose = opt["dose_mg"]
                freq = opt["frequency"]
                lines.append(f"หรือ: {dose} mg × {freq} ครั้ง/วัน")
                if concentration:
                    ml = round(dose / concentration, 2)
                    total_ml = round(ml * freq, 2)
                    lines.append(f"🧪 เทียบเป็น: {ml} ml × {freq} = {total_ml} ml/วัน")
        elif "dose_range_mg" in group_data:
            freq = group_data["frequency"]
            for dose in group_data["dose_range_mg"]:
                lines.append(f"💊 ขนาดยา: {dose} mg × {freq} ครั้ง/วัน")
                if concentration:
                    ml = round(dose / concentration, 2)
                    total_ml = round(ml * freq, 2)
                    lines.append(f"🧪 เทียบเป็น: {ml} ml × {freq} = {total_ml} ml/วัน")
        elif "dose_mg_range" in group_data:
            freq = group_data["frequency"]
            for dose in group_data["dose_mg_range"]:
                lines.append(f"💊 ขนาดยา: {dose} mg × {freq} ครั้ง/วัน")
                if concentration:
                    ml = round(dose / concentration, 2)
                    total_ml = round(ml * freq, 2)
                    lines.append(f"🧪 เทียบเป็น: {ml} ml × {freq} = {total_ml} ml/วัน")
        elif "dose_mg" in group_data and "frequency_options" in group_data:
            dose = group_data["dose_mg"]
            for freq in group_data["frequency_options"]:
                lines.append(f"💊 ขนาดยา: {dose} mg × {freq} ครั้ง/วัน")
                if concentration:
                    ml = round(dose / concentration, 2)
                    total_ml = round(ml * freq, 2)
                    lines.append(f"🧪 เทียบเป็น: {ml} ml × {freq} = {total_ml} ml/วัน")

        # ⛔ Max per day
        if "max_mg_per_day" in group_data and concentration:
            max_mg = group_data["max_mg_per_day"]
            max_ml = round(max_mg / concentration, 2)
            lines.append(f"⛔ ขนาดยาสูงสุดต่อวัน: {max_mg} mg")

        # 📝 หมายเหตุ
        note = group_data.get("note")
        if note:
            lines.append(f"📝 หมายเหตุ: {note}")

        return "\n".join(lines)
    
    if drug == "Ferrous drop":
        indication_info = info["indications"][indication]["all_ages"]
        dose_per_kg = indication_info["initial_dose_mg_per_kg_per_day"]
        freqs = indication_info["frequency"]
        max_range = indication_info["max_dose_range_mg_per_day"]
        usual_max = indication_info.get("usual_max_mg_per_day")
        absolute_max = indication_info.get("absolute_max_mg_per_day")

        total_mg_day = weight * dose_per_kg
        total_mg_day = min(max(total_mg_day, max_range[0]), max_range[1])
        if absolute_max:
            total_mg_day = min(total_mg_day, absolute_max)

        reply_lines = [f"{drug} - {indication} (น้ำหนัก {weight} kg):"]
        reply_lines.append(f"💊 {dose_per_kg} mg/kg/day → {total_mg_day:.1f} mg/day")

        for freq in freqs:
            reply_lines.append(f"→ {freq} ครั้ง/วัน → ครั้งละ ~{(total_mg_day / freq):.1f} mg")

        if "note" in indication_info:
            reply_lines.append(f"\n📌 หมายเหตุ: {indication_info['note']}")

        return "\n".join(reply_lines)

    # กรณีพิเศษอื่น ๆ เช่น Paracetamol (ใช้แบบเดิม)
    if drug == "Paracetamol":
        indication_info = next(iter(info["indications"].values()))
        for entry in indication_info:
            if entry["min_age_years"] <= age < entry["max_age_years"]:
                dose_min_mg = 10 * weight
                dose_max_mg = 15 * weight
                concentration = info["concentration_mg_per_ml"]

                dose_min_ml = dose_min_mg / concentration
                dose_max_ml = dose_max_mg / concentration

                freq = entry["frequency"]
                freq_text = f"{min(freq)}–{max(freq)} ชั่วโมง" if isinstance(freq, list) else f"{freq} ชั่วโมง"

                return (
                    f"{drug} (อายุ {age} ปี, น้ำหนัก {weight} kg):\n"
                    f"💊 ขนาดยา: 10–15 mg/kg/dose → {dose_min_mg:.0f} – {dose_max_mg:.0f} mg/dose\n"
                    f"🥄 ประมาณ {dose_min_ml:.1f} – {dose_max_ml:.1f} ml ต่อครั้ง\n"
                    f"⏱️ ทุก {freq_text} เมื่อมีอาการ\n\n"
                    f"📌 หมายเหตุ: maximum daily dose: 75 mg/kg/day (ไม่เกิน 4,000 mg/day)"
                )

    return f"❌ ไม่พบขนาดยาที่เหมาะสมสำหรับอายุ {age} ปีใน {drug}"


def send_special_indication_carousel(event, drug_name):
    drug_info = SPECIAL_DRUGS.get(drug_name)
    if not drug_info or "indications" not in drug_info:
        messaging_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=f"ไม่พบข้อบ่งใช้ของ {drug_name}")]
            )
        )
        return

    indications = drug_info["indications"]
    common = drug_info.get("common_indications", [])

    names_to_show = common
    columns = []

    for name in names_to_show:
        title = name[:40]
        indication_info = indications[name]

        try:
            if isinstance(indication_info, list):
                if drug_name == "Paracetamol" and name == "Fever":
                    dose = "10–15 mg/kg/dose"
                else:
                    dose = indication_info[0].get("dose_mg_per_kg_per_day") or "?"
            elif isinstance(indication_info, dict):
                # หา dose แบบยืดหยุ่น
                sample_group = next(iter(indication_info.values()))
                if isinstance(sample_group, dict):
                    dose = sample_group.get("dose_mg") or sample_group.get("initial_dose_mg") \
                        or sample_group.get("dose_mg_range", ["?"])[0] \
                        or sample_group.get("dose_range_mg", ["?"])[0]
                else:
                    dose = "?"
            else:
                dose = "?"
        except Exception as e:
            dose = "?"

        columns.append(CarouselColumn(
            title=title,
            text=f"{dose} mg",
            actions=[MessageAction(label="เลือก", text=f"Indication: {name}")]
        ))


    carousel_template = CarouselTemplate(columns=columns)
    messages = [TemplateMessage(
        alt_text=f"ข้อบ่งใช้ {drug_name}",
        template=carousel_template
    )]

    messaging_api.reply_message(
        ReplyMessageRequest(
            reply_token=event.reply_token,
            messages=messages
        )
    )
    return

def get_indication_title(indication_dict):
    """
    คืนค่าชื่อย่อยของ indication จาก key ที่เหมาะสม เช่น label, sub_indication, title, name
    """
    for key in ["label", "sub_indication", "title", "name"]:
        if key in indication_dict:
            return indication_dict[key]
    return None

def create_quick_reply_items(drug, drug_info):
    items = []

    for indication_name, entry in drug_info["indications"].items():
        if isinstance(entry, list):
            for idx, sub in enumerate(entry):
                title = get_indication_title(sub) or f"{indication_name} #{idx+1}"
                label = title[:20]  # LINE จำกัด label ไม่เกิน 20 ตัวอักษร
                items.append(
                    QuickReplyButton(
                        action=PostbackAction(
                            label=label,
                            data=f"{drug}|{indication_name}|{idx}"
                        )
                    )
                )
        else:
            label = indication_name[:20]
            items.append(
                QuickReplyButton(
                    action=PostbackAction(
                        label=label,
                        data=f"{drug}|{indication_name}|0"
                    )
                )
            )
    return items


def get_indication_entry(drug, indication_name, entry_index=0):
    entries = DRUG_DATABASE[drug]["indications"][indication_name]
    if isinstance(entries, list):
        return entries[int(entry_index)]
    return entries

@handler.add(MessageEvent)
def handle_message(event: MessageEvent):
    if not isinstance(event.message, TextMessageContent):
        return
    user_id = event.source.user_id
    text = event.message.text.strip()
    text_lower = text.lower()

    if text_lower in ['คำนวณยา warfarin']:
        user_sessions.pop(user_id, None)
        user_drug_selection.pop(user_id, None)
        user_sessions[user_id] = {"flow": "warfarin", "step": "ask_inr"}
        messaging_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text="🧪 กรุณาใส่ค่า INR (เช่น 2.5)")]
            )
        )
        return

    elif text_lower in ['คำนวณขนาดยาเด็ก', 'คำนวณยาเด็ก']:
        user_sessions.pop(user_id, None)
        user_drug_selection.pop(user_id, None)
        user_ages.pop(user_id, None)
        send_drug_selection(event)
        return
    
    # --------------------------
    # ดำเนิน Warfarin flow
    # --------------------------
    if user_id in user_sessions:
        session = user_sessions[user_id]
        if session.get("flow") == "warfarin":
            step = session.get("step")
            
            if step == "ask_inr":
                try:
                    session["inr"] = float(text)
                    session["step"] = "ask_twd"
                    reply = "📈 ใส่ Total Weekly Dose (TWD) เช่น 28"
                except:
                    reply = "❌ กรุณาใส่ค่า INR เป็นตัวเลข เช่น 2.5"
                messaging_api.reply_message(
                    ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=reply)])
                )
                return

            elif step == "ask_twd":
                try:
                    session["twd"] = float(text)
                    session["step"] = "ask_bleeding"
                    reply = "🩸 มี major bleeding หรือไม่? (yes/no)"
                except:
                    reply = "❌ กรุณาใส่ค่า TWD เป็นตัวเลข เช่น 28"
                messaging_api.reply_message(
                    ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=reply)])
                )
                return

            elif step == "ask_bleeding":
                if text.lower() not in ["yes", "no"]:
                    reply = "❌ ตอบว่า yes หรือ no เท่านั้น"
                    messaging_api.reply_message(
                        ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=reply)])
                    )
                    return
                session["bleeding"] = text.lower()
                session["step"] = "choose_supplement"
                print("[DEBUG] Sending Flex supplement picker now...")
                send_supplement_flex(event)
                return  # ← ตรงนี้สำคัญ

            elif step == "choose_supplement":
                if text == "ไม่ได้ใช้":
                    result = calculate_warfarin(session["inr"], session["twd"], session["bleeding"], "")
                    user_sessions.pop(user_id, None)
                    messaging_api.reply_message(
                        ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=result)])
                    )
                elif text in ["ใช้หลายชนิด", "สมุนไพร/อาหารเสริมชนิดอื่นๆ"]:
                    session["step"] = "ask_supplement"
                    reply = "🌿 โปรดพิมพ์ชื่อสมุนไพรหรืออาหารเสริมที่ใช้อยู่ เช่น กระเทียม, โสม, ขมิ้น"
                    messaging_api.reply_message(
                        ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=reply)])
                    )
                else:
                    result = calculate_warfarin(session["inr"], session["twd"], session["bleeding"], text)
                    user_sessions.pop(user_id, None)
                    messaging_api.reply_message(
                        ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=result)])
                    )
                return

            elif step == "ask_supplement":
                supplement = text.strip()
                result = calculate_warfarin(session["inr"], session["twd"], session["bleeding"], supplement)
                user_sessions.pop(user_id, None)
                messaging_api.reply_message(
                    ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=result)])
                )
                return
        
    if text == "เลือกยาใหม่":
        user_drug_selection.pop(user_id, None)
        user_ages.pop(user_id, None)
        send_drug_selection(event)
        return

    if text.startswith("MoreIndication:"):
        drug_name = text.replace("MoreIndication:", "").strip()
        send_indication_carousel(event, drug_name, show_all=True)
        return

    if text.startswith("เลือกยา:"):
        drug_name = text.replace("เลือกยา:", "").strip()
        user_drug_selection[user_id] = {"drug": drug_name}

        if drug_name in DRUG_DATABASE:
            send_indication_carousel(event, drug_name)
        else:
            send_special_indication_carousel(event, drug_name)
        return

    if text.startswith("Indication:") and user_id in user_drug_selection:
        indication = text.replace("Indication:", "").strip()
        user_drug_selection[user_id]["indication"] = indication
        drug = user_drug_selection[user_id].get("drug")

        if user_id in user_ages:
            user_ages.pop(user_id)

        if drug in SPECIAL_DRUGS:
            example_age = random.randint(1, 18)
            messaging_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=f"📆 กรุณาพิมพ์อายุของเด็ก เช่น {example_age} ปี")]
                )
            )
        else:
            example_weight = round(random.uniform(5.0, 20.0), 1)
            messaging_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=f"เลือกข้อบ่งใช้ {indication} แล้ว กรุณาพิมพ์น้ำหนักเป็นกิโลกรัม เช่น {example_weight}")]
                )
            )
        return
    
    if user_id in user_drug_selection:

        # 🛠 แก้การจับอายุ: ใช้ .group(0) และใส่ try-except
        text_lower = text.lower()

        if any(kw in text_lower for kw in ["ปี", "y", "ขวบ", "เดือน", "mo"]):
            try:
                years = 0
                months = 0

                year_match = re.search(r"(\d+(?:\.\d+)?)\s*(ปี|y|ขวบ)", text_lower)
                if year_match:
                    years = float(year_match.group(1))

                month_match = re.search(r"(\d+(?:\.\d+)?)\s*(เดือน|mo)", text_lower)
                if month_match:
                    months = float(month_match.group(1))

                if not year_match and not month_match:
                    number_match = re.match(r"^\d+(\.\d+)?$", text)
                    if number_match:
                        age_years = float(text)
                    else:
                        raise ValueError("ไม่พบปีหรือเดือน")
                else:
                    age_years = round(years + months / 12, 2)

                if 0 <= age_years <= 18:
                    user_ages[user_id] = age_years
                    user_sessions[user_id] = {"flow": "ask_weight"}
                    example_weight = round(random.uniform(5.0, 20.0), 1)
                    messaging_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=event.reply_token,
                            messages=[TextMessage(text=f"🎯 อายุ {age_years:.2f} ปีแล้ว กรุณาใส่น้ำหนัก เช่น {example_weight} กก")]
                        )
                    )
                else:
                    messaging_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=event.reply_token,
                            messages=[TextMessage(text="❌ กรุณาใส่อายุระหว่าง 0–18 ปี (หรือเป็นเดือนก็ได้)")]
                        )
                    )
                return
            except Exception as e:
                logging.info(f"❌ แปลงอายุไม่ได้: {e}")
                messaging_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text="❌ กรุณาใส่อายุให้ถูกต้อง เช่น 6 เดือน หรือ 1.2 ปี")]
                    )
                )
                return


        if any(kw in text_lower for kw in ["น้ำหนัก", "กก", "kg"]) or text.replace(".", "", 1).isdigit():
            weight_match = re.search(r"(\d+(\.\d+)?)", text)
            if weight_match:
                try:
                    weight = float(weight_match.group(1))
                except ValueError:
                    messaging_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=event.reply_token,
                            messages=[TextMessage(text="❌ กรุณาพิมพ์น้ำหนักให้ถูกต้อง เช่น 20 กก")]
                        )
                    )

                entry = user_drug_selection[user_id]
                drug = entry.get("drug")

                if drug in SPECIAL_DRUGS:
                    age = user_ages.get(user_id)
                    if age is None:
                        # แจ้งให้ใส่อายุก่อน แล้วค่อยพิมพ์น้ำหนักอีกครั้ง
                        messaging_api.reply_message(
                            ReplyMessageRequest(
                                reply_token=event.reply_token,
                                messages=[TextMessage(text="📆 กรุณาพิมพ์อายุของเด็กก่อน เช่น 5 ปี\nจากนั้นพิมพ์น้ำหนักอีกครั้ง")]
                            )
                        )
                        return  # หยุดการทำงานที่นี่เลย
                    else:
                        try:
                            reply = calculate_special_drug(user_id, drug, weight, age)
                        except Exception as e:
                            logging.info(f"❌ คำนวณผิดพลาดใน SPECIAL_DRUG: {e}")
                            reply = "เกิดข้อผิดพลาดในการคำนวณยา"
                else:
                    if "indication" not in entry:
                        reply = "❗️ กรุณาเลือกข้อบ่งใช้ก่อน เช่น 'Indication: Fever'"
                    else:
                        indication = entry["indication"]
                        try:
                            reply = calculate_dose(drug, indication, weight)
                        except Exception as e:
                            logging.info(f"❌ คำนวณผิดพลาดใน DRUG_DATABASE: {e}")
                            reply = "เกิดข้อผิดพลาดในการคำนวณยา"

                messaging_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text=reply)]
                    )
                )
                return

        else:
            # ถ้าไม่มีคำว่า "อายุ" หรือ "น้ำหนัก" ให้แจ้งเตือน
            messaging_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text="❗️ กรุณาพิมพ์อายุ เช่น '5 ปี' หรือ น้ำหนัก เช่น '18 กก'")]
                )
            )
            return

    if user_id not in user_sessions and user_id not in user_drug_selection:
        messaging_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[
                    TextMessage(text="❓ พิมพ์ 'คำนวณยา warfarin' หรือ 'คำนวณยาเด็ก' เพื่อเริ่มต้นใช้งาน")
                ]
            )
        )
        return
        

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
    