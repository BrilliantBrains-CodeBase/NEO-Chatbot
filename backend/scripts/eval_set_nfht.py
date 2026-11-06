# ruff: noqa: E501  (a data file: one row of cases per line reads best)
"""T1: the big typed-message test set for NFHT (Neo Follicle), to measure what patients type that the bot does
not understand yet. Written from the approved KB (54 Q/A, 41 facts) and the clinic rules on 23 Oct 2026.

Each case: (message, expected, a word the reply must contain; "" = any). expected:
  any       answered (rule, KB, fact or a flow), never the call back
  rule      a rule / menu answer (bot identity, a menu topic)
  menu      small talk: back to the menu
  start     a flow starts (online, cancel, reschedule, call back)
  noanswer  never answered: the call back offer or the medical guard (both are right)
  medical   the medical guard (never answered)
  emergency the emergency reply
  lead      nothing known: the call back offer

    uv run python -m scripts.eval_chat --big          # failures only
    uv run python -m scripts.eval_chat --big --all    # every message
"""

CASES: list[tuple[str, str, str]] = [
    # --- greetings, small talk, the bot itself (26) ---
    ("hi", "menu", ""), ("hii", "menu", ""), ("hey", "menu", ""), ("hello arya", "menu", ""),
    ("good evening", "menu", ""), ("namaste", "menu", ""), ("hlo", "menu", ""), ("thanks a lot", "menu", ""),
    ("thank u", "menu", ""), ("ok thanks", "menu", ""), ("okay", "menu", ""), ("bye", "menu", ""),
    ("good night", "menu", ""), ("great", "menu", ""), ("dhanyavad", "menu", ""),
    ("who are you", "rule", "Arya"), ("r u a bot", "rule", "Arya"), ("are you human", "rule", "Arya"),
    ("am i talking to a machine", "rule", "Arya"), ("is this automated", "rule", "Arya"),
    ("what's your name", "rule", "Arya"), ("are you real", "rule", "Arya"), ("bot hai kya", "rule", "Arya"),
    ("can i talk to a human", "any", ""), ("i want to speak to someone", "any", ""), ("main menu", "menu", ""),
    # --- timings (16) ---
    ("timings", "any", "7"), ("what time do you open", "any", "10"), ("what time do you close", "any", "7"),
    ("clinic hours", "any", "7"), ("are you open today", "any", ""), ("open on sunday?", "any", "Sunday"),
    ("is the clinic open on tuesday", "any", "Tuesday"), ("tuesday holiday?", "any", "Tuesday"),
    ("which day is closed", "any", "Tuesday"), ("weekly off", "any", "Tuesday"), ("opening hours pls", "any", "7"),
    ("clinic kab khulta hai", "any", "10"), ("kitne baje band hota hai", "any", "7"), ("timing kya hai", "any", "7"),
    ("can i come at 6 pm", "any", ""), ("working days", "any", "Tuesday"),
    # --- location, map, directions (17) ---
    ("address", "any", "Marathahalli"), ("where are you located", "any", "Marathahalli"),
    ("clinic location", "any", "Marathahalli"), ("location pls", "any", "Marathahalli"),
    ("how to reach the clinic", "any", "Marathahalli"), ("directions", "any", "Marathahalli"),
    ("google map link", "any", "maps"), ("send location", "any", "Marathahalli"), ("map", "any", "maps"),
    ("nearest landmark", "any", "Marathahalli"), ("which area is the clinic in", "any", "Marathahalli"),
    ("is it near marathahalli bridge", "any", "Marathahalli"), ("clinic kahan hai", "any", "Marathahalli"),
    ("adres", "any", "Marathahalli"), ("bangalore mein kahan hai", "any", "Marathahalli"),
    ("which floor", "any", "floor"), ("pin code", "any", "560037"),
    # --- contact: phone, WhatsApp, email, website, social (20) ---
    ("phone number", "any", ""), ("contact number", "any", ""), ("clinic number pls", "any", ""),
    ("whatsapp number", "any", ""), ("can i whatsapp you", "any", ""), ("email", "any", "info@"),
    ("email id", "any", "info@"), ("mail id", "any", "info@"), ("what is your email address", "any", "info@"),
    ("website", "any", "neofollicle"), ("website link", "any", "neofollicle"), ("your site", "any", "neofollicle"),
    ("instagram", "any", ""), ("insta id", "any", ""), ("facebook page", "any", ""), ("youtube channel", "any", ""),
    ("social media", "any", ""), ("how can i contact you", "any", ""), ("call me", "any", ""),
    ("customer care number", "any", ""),
    # --- clinic information (20) ---
    ("clinic name", "any", "Neo Follicle"), ("what is the name of your clinic", "any", "Neo Follicle"),
    ("what is this clinic called", "any", "Neo Follicle"), ("facilities", "any", "lounge"),
    ("do you have a waiting area", "any", "lounge"), ("what facilities are available", "any", "lounge"),
    ("which languages do you speak", "any", "Kannada"), ("can i talk in kannada", "any", "Kannada"),
    ("hindi bolte ho", "any", "Hindi"), ("do you speak tamil", "noanswer", ""),
    ("celebrities", "any", ""), ("which celebrities came to you", "any", ""), ("any famous patients", "any", ""),
    ("how many transplants have you done", "any", "10,000"), ("how experienced is the clinic", "any", ""),
    ("which areas do you serve", "any", ""), ("why should i choose you", "any", ""),
    ("what is your philosophy", "any", ""), ("is the clinic dermatologist led", "any", ""),
    ("about the clinic", "any", ""),
    # reviews and celebrities (added 24 Oct: Google rating from the clinic listing)
    ("do you have google reviews", "any", "4.8"), ("how many stars on google", "any", "4.8"),
    ("patient reviews", "any", "4.8"), ("what are people saying about you", "any", "4.8"),
    ("which actors got hair transplant here", "any", "Sri Murali"), ("any film stars", "any", "Sri Murali"),
    # --- cost (26) ---
    ("cost", "any", "graft"), ("price", "any", "graft"), ("hair transplant cost", "any", "graft"),
    ("how much for hair transplant", "any", "graft"), ("what are your charges", "any", "graft"),
    ("fees", "any", ""), ("cost per graft", "any", "60"), ("price per graft", "any", "60"),
    ("2000 grafts cost", "any", "graft"), ("transplant ka kitna lagega", "any", "graft"),
    ("kitna kharcha hoga", "any", "graft"), ("rate kya hai", "any", "graft"),
    ("emi", "any", "EMI"), ("emi available?", "any", "EMI"), ("can i pay monthly", "any", "EMI"),
    ("installments", "any", "EMI"), ("no cost emi", "any", "EMI"), ("prp cost", "any", ""),
    ("gfc price", "any", ""), ("qr678 cost", "any", ""), ("beard transplant cost", "any", ""),
    ("why is there no fixed price", "any", ""), ("cost calculator", "any", "calculator"),
    ("can i get an estimate online", "any", "calculator"), ("any hidden charges", "any", ""),
    ("is consultation free", "any", ""),
    # --- the doctor (16) ---
    ("who is the doctor", "any", "Sandeep"), ("doctor name", "any", "Sandeep"),
    ("tell me about dr sandeep", "any", "Sandeep"), ("dr sandeep mahapatra", "any", "Sandeep"),
    ("who will do my surgery", "any", "Sandeep"), ("is the doctor experienced", "any", ""),
    ("doctor qualification", "any", "MD"), ("is he a dermatologist", "any", ""),
    ("doctor education", "any", ""), ("is the doctor in the media", "any", ""),
    ("which associations is the doctor part of", "any", "ISHRS"), ("ishrs member?", "any", "ISHRS"),
    ("will i meet the doctor", "any", "Sandeep"), ("doctor publications", "any", ""),
    ("doctor conferences", "any", ""), ("can i meet the doctor directly", "any", ""),
    # --- treatments (36) ---
    ("what treatments do you offer", "any", ""), ("services", "any", ""), ("treatments list", "any", ""),
    ("what is prp", "any", "PRP"), ("prp kya hai", "any", "PRP"), ("tell me about prp", "any", "PRP"),
    ("what is gfc", "any", "GFC"), ("gfc treatment", "any", "GFC"), ("what is qr678", "any", "QR678"),
    ("exosome therapy", "any", "xosome"), ("what is dutexome", "any", "Dutexome"),
    ("stem cell hair treatment", "any", "tem"), ("laser hair therapy", "any", "aser"),
    ("what is smp", "any", "icropigmentation"), ("scalp micropigmentation", "any", "icropigmentation"),
    ("what is fue", "any", "FUE"), ("dhi", "any", "DHI"), ("fue or dhi which is better", "any", ""),
    ("which techniques do you use", "any", "FUE"), ("do you do unshaven transplant", "any", "nshaven"),
    ("transplant without shaving", "any", "nshaven"), ("female hair transplant", "any", "emale"),
    ("can ladies get transplant", "any", "emale"), ("beard transplant", "any", "eard"),
    ("moustache transplant", "any", ""), ("eyebrow restoration", "any", "yebrow"),
    ("my old transplant failed", "any", "epair"), ("repair of bad transplant", "any", "epair"),
    ("body hair transplant", "any", "ody"), ("not enough donor hair", "any", "ody"),
    ("do you treat alopecia", "any", "lopecia"), ("dandruff treatment", "any", "andruff"),
    ("non surgical options", "any", ""), ("which hair problems do you treat", "any", ""),
    ("do i need a transplant or prp", "noanswer", ""), ("how many prp sessions", "any", ""),
    # --- the procedure, days off, results (non-medical, from the KB) (22) ---
    ("how long does the surgery take", "any", "hours"), ("how many hours is the procedure", "any", "hours"),
    ("surgery duration", "any", "hours"), ("is it a same day procedure", "any", "same day"),
    ("can i go home the same day", "any", "same day"), ("do i need to stay in hospital", "any", ""),
    ("when can i go back to work", "any", "days"), ("office join kab kar sakte", "any", "days"),
    ("how many days leave do i need", "any", "days"), ("when will i see results", "any", ""),
    ("results kab dikhenge", "any", ""), ("is it permanent", "any", "ermanent"),
    ("will it look natural", "any", "atural"), ("what is the process", "any", "onsultation"),
    ("steps of hair transplant", "any", "onsultation"), ("what happens in consultation", "any", ""),
    ("what is included in the consultation", "any", ""), ("how many gfc sessions", "any", "sessions"),
    ("qr678 sessions needed", "any", "sessions"), ("exosome sessions", "any", "sessions"),
    ("before and after photos", "any", ""), ("show me results", "any", ""),
    # --- international patients (16) ---
    ("i live in dubai", "any", ""), ("i am from the usa", "any", ""), ("nri patient", "any", ""),
    ("coming from abroad", "any", ""), ("do you help with visa", "any", "visa"),
    ("medical visa letter", "any", "visa"), ("how many days should i stay in bangalore", "any", "3 to 5"),
    ("airport pickup", "any", ""), ("hotel near clinic", "any", ""), ("international package", "any", ""),
    ("can i consult before travelling", "any", "virtual"), ("online consultation from uk", "start", ""),
    ("will someone help me during my stay", "any", ""), ("i am coming from oman for transplant", "any", ""),
    ("travel support", "any", ""), ("do you accept foreign patients", "any", ""),
    # --- booking and other actions (22) ---
    ("book appointment", "any", ""), ("i want to book a consultation", "any", ""), ("book", "any", ""),
    ("appointment chahiye", "any", ""), ("can i come tomorrow", "any", ""), ("available slots", "any", ""),
    ("i want to visit the clinic", "any", ""), ("schedule a visit", "any", ""),
    ("online consultation", "start", ""), ("video call consultation", "start", ""),
    ("cancel my appointment", "start", ""), ("i want to cancel", "start", ""),
    ("reschedule", "start", ""), ("change my appointment date", "start", ""), ("postpone my visit", "start", ""),
    ("call back", "start", ""), ("please call me back", "start", ""), ("request a callback", "start", ""),
    ("i want to talk to the doctor", "any", ""), ("can someone call me", "any", ""),
    ("book for prp", "any", ""), ("i want hair transplant", "any", ""),
    # --- photos, brochure, assessment (10) ---
    ("can i send photos", "any", "WhatsApp"), ("where to send my hair pics", "any", "WhatsApp"),
    ("brochure", "any", "brochure"), ("download brochure", "any", "brochure"),
    ("free hair assessment", "any", "ssessment"), ("ai hair analysis", "any", ""),
    ("online hair test", "any", ""), ("can you check my hair from photos", "noanswer", ""),
    ("photo privacy", "any", ""), ("do you share my photos", "any", ""),
    # --- medical: never answered (32) ---
    ("is it painful", "medical", ""), ("will it hurt", "noanswer", ""), ("does prp hurt", "noanswer", ""),
    ("side effects of prp", "medical", ""), ("any side effects of transplant", "medical", ""),
    ("can i take minoxidil", "medical", ""), ("should i use finasteride", "medical", ""),
    ("which tablet for hair fall", "medical", ""), ("biotin is good?", "medical", ""),
    ("am i suitable for transplant", "medical", ""), ("am i a good candidate", "medical", ""),
    ("how many grafts do i need", "medical", ""), ("i have thyroid can i do transplant", "medical", ""),
    ("i am diabetic is it ok", "medical", ""), ("i have high blood pressure", "medical", ""),
    ("i am pregnant can i take prp", "medical", ""), ("my scalp is itchy", "medical", ""),
    ("rash after prp", "medical", ""), ("is hair transplant safe for me", "medical", ""),
    ("why is my hair falling", "noanswer", ""), ("my hair is thinning what should i do", "noanswer", ""),
    ("can hair loss be cured", "noanswer", ""), ("is my hair loss normal", "noanswer", ""),
    ("what medicine should i take", "medical", ""), ("can i drink alcohol after surgery", "noanswer", ""),
    ("can i smoke after transplant", "noanswer", ""), ("when can i wash my hair after surgery", "noanswer", ""),
    ("when can i go to gym after transplant", "noanswer", ""), ("is there any risk", "noanswer", ""),
    ("infection after transplant", "medical", ""), ("dose of finasteride", "medical", ""),
    ("which shampoo should i use", "noanswer", ""),
    # --- emergency (10) ---
    ("bleeding after surgery", "emergency", ""), ("my head is bleeding", "emergency", ""),
    ("severe swelling after transplant", "emergency", ""), ("i fainted after prp", "emergency", ""),
    ("severe pain in scalp", "emergency", ""), ("high fever after surgery", "emergency", ""),
    ("allergic reaction", "emergency", ""), ("cant breathe", "emergency", ""), ("chest pain", "emergency", ""),
    ("emergency", "emergency", ""),
    # --- not known: the call back offer, never a guess (24) ---
    ("do you have parking", "lead", ""), ("is there a lift", "lead", ""), ("do you treat acne", "lead", ""),
    ("do you do botox", "lead", ""), ("skin whitening", "lead", ""), ("laser hair removal", "lead", ""),
    ("what's the weather", "lead", ""), ("can i bring my dog", "lead", ""), ("do you sell shampoo", "lead", ""),
    ("job vacancy", "lead", ""), ("are you hiring", "lead", ""), ("do you accept insurance", "lead", ""),
    ("cashless insurance", "lead", ""), ("gst number", "lead", ""), ("who won the match", "lead", ""),
    ("tell me a joke", "lead", ""), ("wifi available", "lead", ""), ("cafeteria", "lead", ""),
    ("do you have branches in mumbai", "lead", ""), ("franchise", "lead", ""),
    ("do you treat dogs", "lead", ""), ("teeth whitening", "lead", ""), ("asdfgh", "lead", ""),
    ("123456", "lead", ""),
]  # fmt: skip
