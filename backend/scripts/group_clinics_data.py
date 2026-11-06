# ruff: noqa: E501  (the clinics' own wording, kept whole)
"""The Neo Group's other clinics, as their websites showed them on 6 Nov 2026 (scripts/group_clinics.py loads
them). Treatment descriptions are the sites' own words where the site gave one; empty otherwise. The team
members are placeholders, to be replaced with the real staff before going live."""

from typing import Any

# Weekdays as the database counts them: Sunday 0 ... Saturday 6.
TUESDAY = 2


def items(base: str, rows: list[tuple[str, str, str]]) -> list[dict[str, str]]:
    return [{"name": n, "page": base + p if p else "", "description": d} for n, p, d in rows]


DS = "https://dermasolutions.co.in"
NF = "https://neofertility.co.in"
NS = "https://neosculpt6.com"

CLINICS: list[dict[str, Any]] = [
    {
        "code": "DS",
        "name": "Derma Solutions",
        "full_name": "Derma Solutions Skin & Hair Clinic",
        "website": DS,
        "phone": "+919741223217",
        "phone_label": "+91 97412 23217",
        "whatsapp": "+919741223217",
        "email": "sandeep.mahapatra@dermasolutions.co.in",
        "address": "1st Floor, Scorpio House, near Marathahalli Bridge, Munnekollal, opposite Purva Apartments",
        "city": "Bengaluru",
        "state": "Karnataka",
        "postal_code": "560037",
        "maps_link": "https://www.google.com/maps/dir/?api=1&destination=12.956707,77.707275",
        "landmark": "Near Marathahalli Bridge, opposite Purva Apartments",
        "open": "10:00",
        "close": "20:00",
        "closed": [TUESDAY],
        "hours_text": "Monday and Wednesday to Sunday, 10 AM to 8 PM. Tuesday closed.",
        "online": False,
        "specialty": "Dermatology",
        "clinic_type": "Doctor-led skin, hair and aesthetic clinic: dermatology, lasers, anti-ageing, cosmetic "
        "surgery and hair restoration under one roof.",
        "languages": "English, Hindi, Kannada",
        "social": "Facebook: facebook.com/dermasolutionsskinclinic | Instagram: instagram.com/dermasolutionsskinclinic"
        " | LinkedIn: linkedin.com/company/derma-solutions-skin-hair-clinic-in-bangalore | YouTube: "
        "youtube.com/@dermasolutionsclinic",
        "whatsapp_message": "Hi, I would like to know about skin and hair treatment at Derma Solutions.",
        "notsure": "No problem, most patients are not sure at first. The right treatment depends on your skin or "
        "hair concern, so a dermatologist examines you first and explains the options.",
        "cost": "Most treatment costs depend on your skin, the area and the number of sessions, so they are "
        "confirmed after consultation. Guide prices for procedures: scar removal Rs 10,000 to Rs 50,000 per "
        "session, rhinoplasty Rs 1,00,000 to Rs 1,50,000, breast surgery Rs 1,50,000 to Rs 2,00,000, "
        "liposuction Rs 2,00,000, abdominoplasty Rs 2,50,000 (18% GST applies).",
        "results": (
            "See before-and-after results from Derma Solutions patients. Results vary from person to person.",
            [("Photo gallery", DS + "/image-gallery/"), ("Video gallery", DS + "/video-gallery/")],
        ),
        "doctors": [
            {
                "name": "Dr. Sandeep Mahapatra",
                "slug": "sandeep",
                "title": "Founder & Senior Consultant Dermatologist, Cosmetic Expert & Hair Transplant Surgeon",
                "qualifications": "MBBS, MD (Dermatology), Gold Medalist; Certified DHI Hair Transplant Specialist; "
                "Allergan-certified in Botox & Dermal Fillers",
                "about": "Dr. Sandeep Mahapatra is a Senior Consultant Dermatologist, Cosmetic Expert and Hair "
                "Transplant Surgeon, and the Founder of Derma Solutions.",
                "stats": [
                    ("Years experience", "20+"),
                    ("Laser hair removals", "50,000+"),
                    ("Botox", "4,000+"),
                ],
                "profile_url": DS + "/best-dermatologist-in-marathahalli-whitefield-bangalore/",
            },
            {
                "name": "Dr. Sumedha Tirthani",
                "slug": "sumedha",
                "title": "Consultant Dermatologist",
                "qualifications": "MBBS, MD Dermatology (Gold Medalist)",
                "about": "Dr. Sumedha Tirthani is a gold medalist in MD Dermatology who balances medical "
                "excellence with compassionate patient care.",
                "stats": [],
                "profile_url": DS + "/dr-sumedha-tirthani-dermatologist/",
            },
            {
                "name": "Dr. Thyagaraj",
                "slug": "thyagaraj",
                "title": "Senior Plastic Surgeon",
                "qualifications": "MBBS, MS (General Surgery), MCh (Plastic Surgery), Masters in Reconstructive "
                "Breast Surgery",
                "about": "Dr. Thyagaraj is a senior plastic surgeon at Derma Solutions, recognized for his skill in "
                "plastic and reconstructive surgery.",
                "stats": [("Years experience", "20+")],
                "profile_url": DS + "/dr-thyagaraj-best-plastic-surgeon-in-bangalore/",
            },
            {
                "name": "Dr. Chandhana Vishal N",
                "slug": "chandhana",
                "title": "Plastic, Reconstructive & Aesthetic Surgeon",
                "qualifications": "MBBS, MCh (Plastic Surgery), International Fellowship in Aesthetic Surgery "
                "(Madrid, Spain)",
                "about": "Dr. Chandhana Vishal N is a plastic, reconstructive and aesthetic surgeon with an MCh in "
                "Plastic Surgery and international fellowship training in aesthetic surgery from Madrid, Spain.",
                "stats": [],
                "profile_url": DS + "/dr-chandhana-vishal-n-plastic-surgeon/",
            },
        ],
        "groups": [
            {
                "id": "cosmetology",
                "label": "Cosmetology",
                "items": items(
                    DS,
                    [
                        ("Acne Scar Treatment", "/acne-scar-treatment-in-bangalore/", ""),
                        (
                            "MNRF Treatment",
                            "/mnrf-treatment-in-bangalore-microneedling-with-radio-frequency/",
                            "",
                        ),
                        (
                            "HydraFacial Treatment",
                            "/best-hydrafacial-treatment-in-marathahalli-whitefield-bangalore/",
                            "",
                        ),
                        ("Hollywood Facial", "/hollywood-facial-carbon-laser-peel-bangalore/", ""),
                        ("Chemical Peels", "/chemical-peel-treatment-in-bangalore/", ""),
                        ("Skin Boosters", "/skin-boosters-treatment-in-bangalore/", ""),
                        ("Salmon Sperm PDRN Facial", "/salmon-sperm-pdrn-facial-in-bangalore/", ""),
                        ("Microdermabrasion Treatment", "/microdermabrasion-treatment-in-bangalore/", ""),
                        ("Skin Lightening", "/skin-lightening-treatment-in-bangalore/", ""),
                        (
                            "Dermato Surgery",
                            "/dermato-surgery-in-bangalore/",
                            "Removal of moles, cysts, warts and skin tags, acne scar revision and vitiligo surgery.",
                        ),
                    ],
                ),  # fmt: skip
            },
            {
                "id": "laser",
                "label": "Laser Treatment",
                "items": items(
                    DS,
                    [
                        ("Laser Hair Removal", "/laser-hair-removal-in-bangalore/", ""),
                        ("Laser Skin Toning", "/laser-toning-treatment-in-bangalore/", ""),
                        ("CO2 Fractional Laser", "/fractional-co2-laser-skin-resurfacing-in-bangalore/", ""),
                        ("Mole Removal", "/mole-removal-treatment-in-bangalore/", ""),
                        ("Wart Removal", "/warts-removal-treatment-in-bangalore/", ""),
                        ("Laser Tattoo Removal", "/laser-tattoo-removal-in-bangalore/", ""),
                    ],
                ),  # fmt: skip
            },
            {
                "id": "antiageing",
                "label": "Anti-Ageing Treatment",
                "items": items(
                    DS,
                    [
                        ("Botox", "/botox-treatment-in-bangalore-whitefield-and-marathahalli/", ""),
                        ("Dermal Fillers Treatment", "/dermal-fillers-treatment-bangalore/", ""),
                        ("Skin Tightening", "/skin-tightening-treatment-in-marathahalli-whitefield/", ""),
                        ("Radio Frequency Treatment", "/radio-frequency-skin-tightening-treatment/", ""),
                        ("HIFU Treatment", "/hifu-treatment-in-bangalore/", ""),
                        ("Thread Lifts", "/thread-lifts/", ""),
                        ("IV Glutathione Treatment", "/iv-glutathione-treatment-in-bangalore/", ""),
                        ("NAD IV Drips", "/nad-iv-drips-treatment-in-bangalore/", ""),
                        ("Weight / Fat Loss Injections", "/weight-loss-injections-in-bangalore/", ""),
                        ("Weight Loss Treatment", "/weight-loss-treatment-in-marathahalli/", ""),
                        ("Inch Reduction", "/inch-reduction-treatment-in-bangalore/", ""),
                    ],
                ),  # fmt: skip
            },
            {
                "id": "surgery",
                "label": "Cosmetic Surgeries",
                "items": items(
                    DS,
                    [
                        ("Xanthelasma Removal", "/xanthelasma-removal-treatment-in-bangalore/", ""),
                        ("Cryolipolysis - CoolSculpting", "/cryolipolysis-coolsculpting-in-bangalore/", ""),
                        ("Ear Lobe Repair Surgery", "/ear-lobe-repair-surgery-in-bangalore/", ""),
                        (
                            "Abdominoplasty (Tummy Tuck)",
                            "/abdominoplasty-tummy-tuck-treatment-in-bangalore/",
                            "Restore the contours of your abdomen with a tummy tuck.",
                        ),
                        (
                            "Rhinoplasty Surgery",
                            "/rhinoplasty-surgery-in-bangalore/",
                            "Enhance the shape and function of your nose with rhinoplasty, also known as a nose job.",
                        ),
                        (
                            "Vitiligo Treatment",
                            "/vitiligo-laser-treatment-in-bangalore/",
                            "Uses advanced technology to help restore skin pigmentation.",
                        ),
                        (
                            "Breast Surgeries",
                            "/breast-surgeries-in-bangalore/",
                            "From augmentation to reduction and reconstruction, designed to meet different needs.",
                        ),
                        (
                            "Phototherapy Treatment",
                            "/phototherapy-treatment-in-bangalore/",
                            "Treatment for skin conditions including psoriasis, eczema and vitiligo.",
                        ),
                        (
                            "Liposuction",
                            "/liposuction-treatment-in-bangalore/",
                            "A procedure that removes stubborn fat deposits and enhances your natural contours.",
                        ),
                        (
                            "Gynecomastia Surgery",
                            "/gynecomastia-surgery-in-bangalore/",
                            "Treats male breast enlargement and restores a masculine chest contour.",
                        ),
                    ],
                ),  # fmt: skip
            },
            {
                "id": "hair",
                "label": "Hair Services",
                "items": items(
                    DS,
                    [
                        ("Hair Transplant", "/hair-transplant-in-bangalore-marathahalli-whitefield/", ""),
                        ("GFC Hair Treatment", "/gfc-hair-treatment-in-bangalore/", ""),
                        ("Hair Loss Treatment", "/best-hair-loss-treatment-in-bangalore/", ""),
                        ("Hair Analysis", "/hair-analysis-in-bangalore/", ""),
                    ],
                ),  # fmt: skip
            },
        ],
        "booking_options": [
            "Skin & Acne",
            "Laser Treatment",
            "Anti-Ageing (Botox, Fillers)",
            "Cosmetic Surgery",
            "Hair Treatment",
            "Not sure yet",
            "Other",
        ],  # fmt: skip
        "not_offered": ["ivf", "iui", "fertility", "pregnancy", "delivery", "gynecology", "teeth", "dental"],
        "reviews": [
            (
                "Neha Sharma",
                "skin",
                "Dr. Sandeep is humble, calm and made me feel comfortable throughout my skin treatment.",
            ),
            (
                "Girivasan Sankaran",
                "acne",
                "Explained the root cause and gave me an easy-to-follow treatment plan.",
            ),
            ("Raj Chaudry", "skin", "My skin texture and tone improved noticeably."),
            ("Lalit Kumar Jha", "scar", "The marks have significantly faded, giving me renewed confidence."),
            ("Mridula Pardeshi", "botox", "Fine lines and wrinkles on my face were visibly reduced."),
            ("Sara Bansal", "threads", "PDO thread lifts gave an instant lift to my cheeks and jawline."),
        ],  # fmt: skip
        "team": [
            ("Kavya Menon", "clinic_manager"),
            ("Rohan Das", "front_desk"),
            ("Sneha Iyer", "front_desk"),
        ],
    },
    {
        "code": "NF",
        "name": "Neo Fertility",
        "full_name": "Neo Fertility Clinic",
        "website": NF,
        "phone": "+917337761236",
        "phone_label": "+91 73377 61236",
        "whatsapp": "+917337761236",
        "email": "care@neofertility.co.in",
        "address": "1st floor, Scorpio House, Marathahalli Bridge Service Road, Munnekolala, opposite Purva "
        "Apartments",
        "city": "Bengaluru",
        "state": "Karnataka",
        "postal_code": "560037",
        "maps_link": "https://www.google.com/maps?cid=1851221529633718164",
        "landmark": "Marathahalli Bridge Service Road, opposite Purva Apartments",
        "open": "09:30",
        "close": "18:30",
        "closed": [],
        "hours_text": "All seven days, 9:30 AM to 6:30 PM.",
        "online": False,
        "specialty": "Fertility and Gynecology",
        "clinic_type": "Fertility and gynecology clinic led by Dr. Payal Mahapatra: IUI, IVF, ICSI, egg freezing, "
        "pregnancy care and gynecology.",
        "languages": "",
        "social": "Facebook: facebook.com/NeoFertilityClinic | Instagram: instagram.com/neofertilityclinic | "
        "LinkedIn: linkedin.com/company/neo-fertility-clinic | YouTube: youtube.com/@NeoFertilityIVFClinicBengaluru",
        "whatsapp_message": "Hi, I found Neo Fertility Clinic online and would like to book an appointment.",
        "notsure": "No problem. The right treatment depends entirely on the diagnosis, so Dr. Payal evaluates both "
        "partners first and explains the options. No referral is needed.",
        "cost": "A written estimate is given at the first consultation. Guide prices: initial consultation and tests "
        "Rs 3,000 to Rs 5,000; IVF cycle Rs 1,00,000 to Rs 2,00,000; full IVF with ICSI Rs 1,80,000 to "
        "Rs 2,50,000; frozen embryo transfer Rs 50,000 to Rs 80,000; TESA or PESA Rs 20,000 to Rs 40,000; "
        "genetic testing (PGT) Rs 1,00,000 and above. Medication varies. EMI and financing are available.",
        "results": (
            "Read stories from Neo Fertility patients and their families.",
            [("Patient stories", NF + "/patient-stories/"), ("Gallery", NF + "/gallery/")],
        ),
        "doctors": [
            {
                "name": "Dr. Payal Mahapatra",
                "slug": "payal",
                "title": "Fertility Specialist and Gynecologist",
                "qualifications": "MBBS, DGO, DNB, Fellowship in Reproductive Medicine (FRM)",
                "about": "Dr. Payal Mahapatra has 18 years of clinical experience in fertility and gynecology, is a "
                "member of ISAR and FOGSI, and founded Neo Fertility Clinic.",
                "stats": [
                    ("Years experience", "18"),
                    ("Patients treated", "80k"),
                    ("IVF cycles", "2k"),
                    ("IUI procedures", "6.7k"),
                ],  # fmt: skip
                "profile_url": NF + "/best-gynecologist-and-fertility-doctor-in-marathahalli/",
            },
        ],
        "groups": [
            {
                "id": "fertility",
                "label": "Fertility Treatment",
                "items": items(
                    NF,
                    [
                        (
                            "Infertility Evaluation & Treatment",
                            "/infertility-treatment-in-marathahalli-whitefield-in-bangalore/",
                            "A step-by-step evaluation for couples trying to conceive.",
                        ),
                        (
                            "Intrauterine Insemination (IUI)",
                            "/intrauterine-insemination-iui-treatment-marathahalli-whitefield-in-bangalore/",
                            "A simple, minimally invasive treatment that places healthy sperm directly in the uterus.",
                        ),
                        (
                            "In-Vitro Fertilization (IVF)",
                            "/best-ivf-treatment-in-marathahalli-whitefield-bangalore/",
                            "One of the most effective fertility treatments. Eggs and sperm are combined in our lab.",
                        ),
                        (
                            "Intracytoplasmic Sperm Injection (ICSI)",
                            "/icsi-treatment-in-marathahalli-whitefield-bangalore/",
                            "An advanced form of IVF where a single healthy sperm is injected directly into the egg.",
                        ),
                        (
                            "Egg Freezing & Preservation",
                            "/best-egg-freezing-clinic-in-marathahalli-bangalore/",
                            "Freeze your healthy eggs today to protect your fertility for tomorrow.",
                        ),
                        (
                            "Male Infertility Treatment",
                            "/best-male-infertility-treatment-in-marathahalli-bangalore/",
                            "Male factors contribute to nearly half of all infertility cases.",
                        ),
                        (
                            "Donor Egg & Sperm Programs",
                            "/donor-eggs-and-sperm-program-in-marathahalli-bangalore/",
                            "Donor programs help couples conceive when pregnancy is not possible with their own eggs or "
                            "sperm.",
                        ),
                    ],
                ),  # fmt: skip
            },
            {
                "id": "pregnancy",
                "label": "Pregnancy Services",
                "items": items(
                    NF,
                    [
                        (
                            "Preconception Checkup",
                            "/best-pre-conception-health-check-in-marathahalli-bangalore/",
                            "A complete health check for both partners before you try to conceive.",
                        ),
                        (
                            "Pregnancy Care",
                            "/best-pregnancy-care-in-marathahalli-whitefield-bangalore/",
                            "Month-by-month expert care through every trimester: regular scans, personalised guidance, and "
                            "a safe delivery plan.",
                        ),
                        (
                            "Natural Delivery",
                            "/natural-delivery-in-marathahalli-whitefield-bangalore/",
                            "Nutrition, movement and close monitoring through pregnancy so a natural birth stays within "
                            "reach.",
                        ),
                        (
                            "Family Planning",
                            "/family-planning-services-in-bangalore/",
                            "Personalised advice on contraception, birth spacing, and reproductive health.",
                        ),
                        (
                            "Pelvic Ultrasound Scan",
                            "/pelvic-ultrasound-scan-in-marathahalli/",
                            "A quick, painless scan to check your uterus, ovaries, and reproductive health.",
                        ),
                    ],
                ),  # fmt: skip
            },
            {
                "id": "hormonal",
                "label": "PCOS, PCOD & Hormonal Care",
                "items": items(
                    NF,
                    [
                        (
                            "PCOD Treatment",
                            "/best-pcod-treatment-in-marathahalli-whitefield-bangalore/",
                            "Expert care for ovarian cysts, irregular periods, and hormonal imbalance.",
                        ),
                        (
                            "PCOS Treatment",
                            "/best-pcos-treatment-in-marathahalli-whitefield-bangalore/",
                            "Complete treatment for PCOS, tackling irregular periods, weight, acne, and fertility issues.",
                        ),
                        (
                            "Irregular or Painful Periods",
                            "/menstrual-bleeding-and-irregular-period-treatment-in-marathahalli-bangalore/",
                            "",
                        ),
                        (
                            "Menopausal Issues",
                            "/menstrual-bleeding-and-irregular-period-treatment-in-marathahalli-bangalore/#menopausal_disorders",
                            "",
                        ),
                    ],
                ),  # fmt: skip
            },
            {
                "id": "gynecology",
                "label": "Gynecology",
                "items": items(
                    NF,
                    [
                        (
                            "STI Treatment",
                            "/sexually-transmitted-infections-stis-treatment-in-bangalore/",
                            "",
                        ),
                        (
                            "Pelvic Inflammatory Disease (PID)",
                            "/pelvic-inflammatory-disease-pids-treatment-in-bangalore/",
                            "",
                        ),
                        (
                            "Vaginal Infection or Discharge",
                            "/vaginal-discharge-infection-treatment-in-marathahalli-bangalore/",
                            "",
                        ),
                        ("Breast Lumps", "/breast-lumps-treatment-in-marathahalli-whitefield-bangalore/", ""),
                        ("Pain During Sex", "/best-doctor-for-pain-during-sex-treatment-in-bangalore/", ""),
                        (
                            "Medical Termination of Pregnancy",
                            "/medical-termination-of-pregnancy-mtp-marathahalli-whitefield/",
                            "",
                        ),
                        ("Hysteroscopy", "/best-hysteroscopy-treatment-in-marathahalli-bangalore/", ""),
                        (
                            "Laparoscopy",
                            "/laparoscopic-surgery-for-infertility-in-marathahalli-bangalore/",
                            "",
                        ),
                    ],
                ),  # fmt: skip
            },
        ],
        "booking_options": [
            "IVF",
            "IUI",
            "ICSI",
            "Fertility Consultation",
            "PCOS / Irregular Cycles",
            "Male Infertility",
            "Pregnancy Care",
            "Gynecology",
            "Not sure yet",
            "Other",
        ],  # fmt: skip
        "not_offered": [
            "hair transplant",
            "hair removal",
            "laser",
            "botox",
            "fillers",
            "acne",
            "tattoo removal",
            "liposuction",
            "rhinoplasty",
            "teeth",
            "dental",
        ],  # fmt: skip
        "reviews": [
            (
                "Sneha Subudhi",
                "ivf",
                "Within just six months of starting treatment with Neo Clinic, I received the "
                "long-awaited positive result.",
            ),
            (
                "Pramila Sahu",
                "fertility",
                "Dr. Payal is the best Fertility Expert and I would highly recommend "
                "Dr. Payal and Neo Fertility Clinic.",
            ),
            (
                "Shruti Gupta",
                "fertility",
                "I would definitely recommend Dr. Payal to anyone struggling with "
                "infertility and looking for a specialist.",
            ),
        ],  # fmt: skip
        "team": [
            ("Priya Nair", "clinic_manager"),
            ("Arjun Reddy", "front_desk"),
            ("Meera Joshi", "front_desk"),
        ],
    },
    {
        "code": "NS6",
        "name": "NeoSculpt6",
        "full_name": "NeoSculpt6",
        "website": NS,
        "phone": "+919964060483",
        "phone_label": "+91 99640 60483",
        "whatsapp": "+919187401600",
        "email": "info@neosculpt6.com",
        "address": "2nd floor, above Honda Big Wings, Sadaramangala Village, Whitefield Main Road",
        "city": "Bengaluru",
        "state": "Karnataka",
        "postal_code": "560066",
        "maps_link": "https://www.google.com/maps/search/?api=1&query=NeoSculpt6%2C%20Sadaramangala%2C%20Whitefield"
        "%20Main%20Road%2C%20Bangalore%20560066",
        "landmark": "Beside BMW Deutsche Motoren, Whitefield Main Road",
        "open": "10:00",
        "close": "20:00",
        "closed": [TUESDAY],
        "hours_text": "Every day except Tuesday, 10 AM to 8 PM.",
        "online": True,
        "specialty": "Aesthetic medicine",
        "clinic_type": "Doctor-led aesthetic clinic in Whitefield, part of the Neo Group: hair, face, skin, laser, "
        "body contouring, cosmetic surgery and intimate wellness.",
        "languages": "",
        "social": "Facebook: facebook.com/profile.php?id=61596274587019 | Instagram: instagram.com/neosculpt6",
        "whatsapp_message": "Hi, I would like to know about treatment at NeoSculpt6.",
        "notsure": "No problem. At NeoSculpt6 you meet the doctor, who assesses your concern first and explains "
        "the options. A video consultation is also possible.",
        "cost": "There is no fixed price: the cost depends on your assessment and plan, and is explained after "
        "consultation, in clinic or by video.",
        "results": (
            "Before-and-after photos and patient stories are shared during your consultation. Results vary from "
            "person to person.",
            [],
        ),
        "intl": "Patients from outside India can start with a video consultation that confirms the plan, cost and "
        "recovery time before they travel.",
        "intl_page": NS + "/hair-transplant-restoration/nri-hair-transplant-consultation-in-bangalore/",
        "analysis": NS + "/hair-assessment/",
        "doctors": [
            {
                "name": "Dr. Sandeep Mahapatra",
                "slug": "sandeep",
                "title": "Founder & Lead Doctor; Senior Consultant Dermatologist, Cosmetic Expert & Hair Transplant "
                "Surgeon",
                "qualifications": "MBBS, MD Dermatology, Venereology & Leprosy (Gold Medalist); Certified DHI "
                "Specialist",
                "about": "For more than two decades Dr Sandeep has treated hair loss, skin and ageing concerns as "
                "medical problems first and cosmetic ones second.",
                "stats": [("Hair transplants", "10,000+"), ("Botox", "4,000+"), ("Fillers", "2,000+")],
                "profile_url": NS + "/about-dr-sandeep-mahapatra/",
            },
            {
                "name": "Dr. Payal Mahapatra",
                "slug": "payal",
                "title": "Fertility Specialist & Gynecologist",
                "qualifications": "MBBS, DGO, DNB, Fellowship in Reproductive Medicine",
                "about": "Dr. Payal Mahapatra is a fertility specialist and gynecologist, a member of ISAR and FOGSI, "
                "and the founder of Neo Fertility Clinic.",
                "stats": [],
                "profile_url": NS + "/dr-payal-mahapatra/",
            },
            {
                "name": "Dr. Thyagaraj",
                "slug": "thyagaraj",
                "title": "Senior Plastic Surgeon",
                "qualifications": "MBBS, MS General Surgery, MCh Plastic Surgery, Masters in Reconstructive Breast "
                "Surgery",
                "about": "Dr. Thyagaraj trained in plastic and reconstructive surgery in India and Europe, and leads "
                "face, breast and body surgery at NeoSculpt6.",
                "stats": [],
                "profile_url": NS + "/dr-thyagaraj/",
            },
            {
                "name": "Dr. Sumedha Tirthani",
                "slug": "sumedha",
                "title": "Consultant Dermatologist",
                "qualifications": "MBBS (Gold Medalist), MD Dermatology (Gold Medalist)",
                "about": "Dr. Sumedha Tirthani is a dermatologist and a gold medalist in MD Dermatology, treating "
                "acne, pigmentation, hair loss and vitiligo.",
                "stats": [],
                "profile_url": NS + "/dr-sumedha-tirthani/",
            },
        ],
        "groups": [
            {
                "id": "hair",
                "label": "Hair Restoration",
                "items": items(
                    NS,
                    [
                        (
                            "FUE Hair Transplant",
                            "/hair-transplant-restoration/fue-hair-transplant-in-bangalore/",
                            "",
                        ),
                        (
                            "DHI Hair Transplant",
                            "/hair-transplant-restoration/dhi-hair-transplant-in-bangalore/",
                            "",
                        ),
                        (
                            "Neo Follicle Transplant (NFT)",
                            "/hair-transplant-restoration/neo-follicle-hair-transplant-in-bangalore/",
                            "",
                        ),
                        (
                            "Female Hair Transplant",
                            "/hair-transplant-restoration/female-hair-transplant-in-bangalore/",
                            "",
                        ),
                        (
                            "Unshaven Hair Transplant",
                            "/hair-transplant-restoration/unshaven-hair-transplant-in-bangalore/",
                            "Suits selected patients who want to avoid a full head shave.",
                        ),
                        (
                            "Beard & Moustache Transplant",
                            "/hair-transplant-restoration/beard-moustache-transplant-in-bangalore/",
                            "",
                        ),
                        (
                            "Eyebrow Transplant",
                            "/hair-transplant-restoration/eyebrow-hair-transplant-in-bangalore/",
                            "",
                        ),
                        (
                            "PRP Hair Treatment",
                            "/hair-transplant-restoration/prp-hair-treatment-in-bangalore/",
                            "",
                        ),
                        (
                            "GFC Hair Treatment",
                            "/hair-transplant-restoration/gfc-hair-treatment-in-bangalore/",
                            "",
                        ),
                        (
                            "QR678 Hair Regrowth",
                            "/hair-transplant-restoration/qr678-hair-regrowth-treatment-in-bangalore/",
                            "",
                        ),
                        (
                            "Scalp Micropigmentation",
                            "/hair-transplant-restoration/scalp-micropigmentation-smp-in-bangalore/",
                            "",
                        ),
                        (
                            "Failed Hair Transplant Repair",
                            "/hair-transplant-restoration/failed-hair-transplant-repair-in-bangalore/",
                            "",
                        ),
                    ],
                ),  # fmt: skip
            },
            {
                "id": "face",
                "label": "Anti-Ageing & Injectables",
                "items": items(
                    NS,
                    [
                        (
                            "Botox Treatment",
                            "/anti-aging-injectables/botox-treatment-in-bangalore/",
                            "Can soften certain movement-based expression lines.",
                        ),
                        (
                            "Dermal Fillers",
                            "/anti-aging-injectables/dermal-filler-treatment-in-bangalore/",
                            "",
                        ),
                        ("Lip Fillers", "/anti-aging-injectables/lip-fillers-in-bangalore/", ""),
                        ("Under Eye Fillers", "/anti-aging-injectables/under-eye-fillers-in-bangalore/", ""),
                        ("Profhilo", "/anti-aging-injectables/profhilo-in-bangalore/", ""),
                        (
                            "Skin Boosters",
                            "/anti-aging-injectables/skin-boosters-treatment-in-bangalore/",
                            "",
                        ),
                        ("PDRN Treatment", "/anti-aging-injectables/pdrn-treatment-in-bangalore/", ""),
                        ("HIFU Treatment", "/anti-aging-injectables/hifu-treatment-in-bangalore/", ""),
                        ("Thread Lift", "/anti-aging-injectables/thread-lift-treatment-in-bangalore/", ""),
                        (
                            "Non-Surgical Face Lift",
                            "/anti-aging-injectables/non-surgical-face-lift-in-bangalore/",
                            "",
                        ),
                        (
                            "Glutathione IV Drip",
                            "/anti-aging-injectables/glutathione-iv-drip-treatment-in-bangalore/",
                            "",
                        ),
                    ],
                ),  # fmt: skip
            },
            {
                "id": "laser",
                "label": "Laser & Skin",
                "items": items(
                    NS,
                    [
                        ("Acne Treatment", "/laser-skin-aesthetic/acne-treatment-in-bangalore/", ""),
                        (
                            "Acne Scar Treatment",
                            "/laser-skin-aesthetic/acne-scar-treatment-in-bangalore/",
                            "",
                        ),
                        (
                            "MNRF Treatment",
                            "/laser-skin-aesthetic/mnrf-treatment-in-bangalore/",
                            "Combines controlled microneedling with radiofrequency.",
                        ),
                        (
                            "Pigmentation Treatment",
                            "/laser-skin-aesthetic/pigmentation-treatment-in-bangalore/",
                            "",
                        ),
                        ("Melasma Treatment", "/laser-skin-aesthetic/melasma-treatment-in-bangalore/", ""),
                        (
                            "Laser Hair Reduction",
                            "/laser-skin-aesthetic/laser-hair-reduction-in-bangalore/",
                            "",
                        ),
                        (
                            "CO2 Fractional Laser",
                            "/laser-skin-aesthetic/co2-fractional-laser-treatment-in-bangalore/",
                            "",
                        ),
                        (
                            "Hydrafacial",
                            "/laser-skin-aesthetic/hydrafacial-in-bangalore/",
                            "Medical-grade, non-invasive skin treatment.",
                        ),
                        ("Chemical Peels", "/laser-skin-aesthetic/chemical-peels-in-bangalore/", ""),
                        ("Laser Mole Removal", "/laser-skin-aesthetic/laser-mole-removal-in-bangalore/", ""),
                        (
                            "Laser Tattoo Removal",
                            "/laser-skin-aesthetic/laser-tattoo-removal-in-bangalore/",
                            "",
                        ),
                    ],
                ),  # fmt: skip
            },
            {
                "id": "body",
                "label": "Body Contouring & Weight",
                "items": items(
                    NS,
                    [
                        (
                            "GLP-1 Weight Loss Program",
                            "/slimming-body-contouring/glp-1-weight-loss-program-in-bangalore/",
                            "",
                        ),
                        (
                            "Medical Weight Loss",
                            "/slimming-body-contouring/medical-weight-loss-treatment-in-bangalore/",
                            "",
                        ),
                        (
                            "Body Contouring",
                            "/slimming-body-contouring/body-contouring-in-bangalore/",
                            "Improves shape, proportion and selected areas, not obesity.",
                        ),
                        (
                            "Cryolipolysis",
                            "/slimming-body-contouring/cryolipolysis-treatment-in-bangalore/",
                            "",
                        ),
                        (
                            "Inch Loss Treatment",
                            "/slimming-body-contouring/inch-loss-treatment-in-bangalore/",
                            "",
                        ),
                        (
                            "Belly & Tummy Fat Reduction",
                            "/slimming-body-contouring/belly-tummy-fat-reduction-in-bangalore/",
                            "",
                        ),
                        (
                            "Double Chin Fat Reduction",
                            "/slimming-body-contouring/double-chin-fat-reduction-in-bangalore/",
                            "",
                        ),
                        (
                            "Stretch Mark Treatment",
                            "/slimming-body-contouring/stretch-mark-treatment-in-bangalore/",
                            "",
                        ),
                        (
                            "Skin Tightening",
                            "/slimming-body-contouring/skin-tightening-treatment-in-bangalore/",
                            "",
                        ),
                    ],
                ),  # fmt: skip
            },
            {
                "id": "surgery",
                "label": "Cosmetic Surgery",
                "items": items(
                    NS,
                    [
                        ("Rhinoplasty", "/cosmetic-surgery/rhinoplasty-in-bangalore/", ""),
                        ("Facelift", "/cosmetic-surgery/facelift-surgery-in-bangalore/", ""),
                        (
                            "Blepharoplasty (Eyelid Surgery)",
                            "/cosmetic-surgery/blepharoplasty-eyelid-surgery-in-bangalore/",
                            "",
                        ),
                        (
                            "Liposuction",
                            "/cosmetic-surgery/liposuction-surgery-in-bangalore/",
                            "Removes chosen pockets of subcutaneous fat through small cannulas.",
                        ),
                        (
                            "Tummy Tuck (Abdominoplasty)",
                            "/cosmetic-surgery/tummy-tuck-surgery-abdominoplasty-in-bangalore/",
                            "",
                        ),
                        ("Mommy Makeover", "/cosmetic-surgery/mommy-makeover-surgery-in-bangalore/", ""),
                        ("Gynaecomastia Surgery", "/cosmetic-surgery/gynecomastia-surgery-in-bangalore/", ""),
                        ("Breast Surgery", "/cosmetic-surgery/breast-augmentation-surgery-in-bangalore/", ""),
                    ],
                ),  # fmt: skip
            },
            {
                "id": "intimate",
                "label": "Intimate Wellness",
                "items": items(
                    NS,
                    [
                        ("Labiaplasty", "/cosmetic-gynecology/labiaplasty-surgery-in-bangalore/", ""),
                        (
                            "Laser Vaginal Tightening",
                            "/cosmetic-gynecology/laser-vaginal-tightening-in-bangalore/",
                            "",
                        ),
                        (
                            "Vaginal Rejuvenation",
                            "/cosmetic-gynecology/vaginal-rejuvenation-treatment-in-bangalore/",
                            "",
                        ),
                        (
                            "Intimate Pigmentation",
                            "/cosmetic-gynecology/intimate-pigmentation-treatment-in-bangalore/",
                            "",
                        ),
                    ],
                ),  # fmt: skip
            },
        ],
        "booking_options": [
            "Hair",
            "Face & Anti-Ageing",
            "Skin & Laser",
            "Body & Weight",
            "Cosmetic Surgery",
            "Private consultation",
            "Not sure yet",
            "Other",
        ],  # fmt: skip
        "not_offered": ["ivf", "iui", "fertility", "pregnancy", "delivery", "teeth", "dental"],
        # The site's testimonials are from its sister clinics and were not read in full: none until the clinic
        # adds its own (Dashboard → Clinic info → Reviews).
        "reviews": [],
        "team": [
            ("Vikram Shetty", "clinic_manager"),
            ("Ananya Kulkarni", "front_desk"),
            ("Rahul Verma", "front_desk"),
        ],  # fmt: skip
    },
]
