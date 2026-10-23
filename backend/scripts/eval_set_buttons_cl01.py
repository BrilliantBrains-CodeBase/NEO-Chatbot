# ruff: noqa: E501  (a data file: one row of cases per line reads best)
"""Button test set for CL01: for every button, how a patient might TYPE it instead of tapping (English).
Worded differently from the training phrases (app/clinics/CL01.intents.json) on purpose, so the score shows
what new patients get. Same format as eval_set_cl01.py; the word proves the right screen opened.

    uv run python -m scripts.eval_chat --buttons
"""

CASES: list[tuple[str, str, str]] = [
    # --- main menu tiles ---
    ("i'd like to make a booking", "start", "book your appointment"), ("can i come in for a visit", "start", "book your appointment"),
    ("i want to get checked at the clinic", "start", "book your appointment"),
    ("show me the treatments", "any", "explore"), ("what treatments are available", "any", "explore"),
    ("tell me about the doctors", "any", ""), ("who are your doctors", "any", ""),
    ("i am an international patient", "any", ""), ("i live in another country", "any", ""),
    ("please call me", "any", ""), ("i want someone to call me", "any", ""),
    ("whatsapp", "any", ""), ("chat on whatsapp", "any", ""),
    # --- booking menu ---
    ("make an appointment at the clinic", "start", "book your appointment"),
    ("video consultation please", "start", "online video"), ("consult online", "start", "online video"),
    ("cancel the booking", "start", "cancel"), ("i won't be coming, cancel it", "start", "cancel"),
    ("change my appointment time", "start", "reschedule"), ("push my appointment to next week", "start", "reschedule"),
    # --- explore treatments ---
    ("hair transplant types", "any", ""), ("what transplant options are there", "any", ""),
    ("hair fall solutions", "any", ""), ("my hair is thinning, what treatments do you have", "any", ""),
    ("i'm not sure which treatment", "any", ""), ("help me pick", "any", ""),
    # --- doctor ---
    ("show dr sandeep's profile", "any", ""), ("about dr. mahapatra", "any", "Sandeep"),
    # --- cost guide ---
    ("cost for a receding hairline", "any", "1,000 to 1,800"), ("my hairline has moved back, what will it cost", "any", "1,000 to 1,800"),
    ("cost for crown thinning", "any", "1,200 to 2,000"), ("bald patch at the crown, price?", "any", "1,200 to 2,000"),
    ("front and crown both are thin, cost?", "any", "2,000 to 3,000"),
    ("price for advanced baldness", "any", "3,000+"), ("i have very little hair left, cost?", "any", "3,000+"),
    ("how much is a beard transplant", "any", ""), ("eyebrow transplant cost", "any", ""),
    ("i don't know my hair loss pattern, what's the cost", "any", ""),
    ("get an exact quote", "any", ""),
    # --- treatment cards ---
    ("prp for hair", "any", "PRP"), ("platelet rich plasma treatment", "any", "PRP"),
    ("gfc for hair loss", "any", "GFC"), ("growth factor therapy", "any", "GFC"),
    ("qr678 treatment", "any", "QR678"), ("exosome treatment", "any", "xosome"),
    ("dutexome", "any", "utexome"), ("stem cell treatment for hair", "any", "tem"),
    ("laser treatment for hair", "any", "aser"), ("scalp pigmentation", "any", "icropigmentation"),
    ("alopecia", "any", "lopecia"), ("bald patches on my head", "any", "lopecia"),
    ("dandruff", "any", "andruff"), ("itchy flakes on scalp", "noanswer", ""),
    ("dhi", "any", "DHI"), ("fue hair transplant", "any", "FUE"),
    ("hair transplant for a man", "any", ""), ("hair transplant for a woman", "any", "emale"),
    ("my last transplant didn't work", "any", "epair"), ("transplant without shaving my head", "any", "nshaven"),
    ("body hair transplant", "any", "ody"), ("beard implant", "any", "eard"), ("eyebrow implant", "any", "yebrow"),
    # --- link buttons ---
    ("call the clinic", "any", ""), ("clinic phone", "any", ""),
    ("open google maps", "any", "maps"), ("directions on map", "any", "Marathahalli"),
    ("ai hair analysis", "any", ""), ("analyse my hair with ai", "any", ""),
    ("patient videos", "any", ""), ("before and after pictures", "any", ""),
    ("beard results", "any", ""), ("celebrity patients", "any", ""),
]  # fmt: skip
