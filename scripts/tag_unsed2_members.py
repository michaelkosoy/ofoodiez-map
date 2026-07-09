import os
import sys
from dotenv import load_dotenv

# Add parent directory to path so we can import the app modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Load env
load_dotenv()

from app import app
from database.models import db, HitechEmail

# List of emails provided by the user (users who already received the email)
EXCLUDED_EMAILS = {
    "hilagez2@gmail.com",
    "yuvalsahar1466@gmail.com",
    "aviglik91@gmail.com",
    "ambar.elad@gmail.com",
    "kerenschoss369@gmail.com",
    "oded456@gmail.com",
    "noa123adler@gmail.com",
    "mnahum@paloaltonetworks.com",
    "or.rahima@gmail.com",
    "yuval.d@astelia.io",
    "shachar.s265@gmail.com",
    "nofarbelo@gmail.com",
    "marin431@gmail.com",
    "pazyohananof@gmail.com",
    "shifris.shachar@gmail.com",
    "yaelmic122@gmail.com",
    "idanyehiel123@gmail.com",
    "cjperez1512@gmail.com",
    "maya6060@gmail.com",
    "noyhammel@gmail.com",
    "nastia.tsiganiyk@gmail.com",
    "mikaross12@gmail.com",
    "danielevron2@gmail.com",
    "yaara@neonsecurity.ai",
    "sivan.vaturi@gmail.com",
    "tamar.raz@appliedsystems.com",
    "nir.kouris@dbank.co.il",
    "nofarboidek@gmail.com",
    "ron1997ron@gmail.com",
    "lavilavi.daniel@gmail.com",
    "netasoto15@gmail.com",
    "lilach@loox.io",
    "shalev.kaveh@gmail.com",
    "ilaygoldman2@gmail.com",
    "yaelco11220@gmail.com",
    "lili24801@gmail.com",
    "yonatanluchter@gmail.com",
    "sapir23487@gmail.com",
    "hadar686@gmail.com",
    "liby.zislis@gmail.com",
    "netaddd@gmail.com",
    "michellebarz@gmail.com",
    "eyal.edri@gmail.com",
    "guy.rosenberg@wsc-sports.com",
    "chenulfan@gmail.com",
    "tamara.ako@gmail.com",
    "amitmichael22@gmail.com",
    "mikiz@gfo.co.il",
    "paz.ben.nun@gmail.com",
    "dteleman@yahoo.com",
    "chen.malobani@gmail.com",
    "yuvalvardi97@gmail.com",
    "liatmen22@gmail.com",
    "zemerhay@gmail.com",
    "nimsi98@gmail.com",
    "rachelbgrand@gmail.com",
    "avishai.sh@gmail.com",
    "rachelshimoni@gmail.com",
    "limoradler7@gmail.com",
    "keren.schweitzer22@gmail.com",
    "lizbethtr@gmail.com",
    "ofir.lazarov@gmail.com"
}

# Normalize excluded emails to lower case and strip whitespace
EXCLUDED_EMAILS = {email.strip().lower() for email in EXCLUDED_EMAILS if email.strip()}

def tag_members():
    print(f"Starting script to tag unsent verified members...")
    print(f"Number of excluded emails: {len(EXCLUDED_EMAILS)}")
    
    with app.app_context():
        # Fetch all verified members
        verified_members = HitechEmail.query.filter_by(verified=True).all()
        print(f"Total verified members in database: {len(verified_members)}")
        
        tagged_count = 0
        skipped_count = 0
        
        for member in verified_members:
            email_normalized = (member.email or '').strip().lower()
            if email_normalized in EXCLUDED_EMAILS:
                skipped_count += 1
                continue
            
            # Tag the member
            member.list_name = "unsed2"
            tagged_count += 1
            
        if tagged_count > 0:
            db.session.commit()
            print(f"✅ Successfully tagged {tagged_count} members with list name 'unsed2'.")
        else:
            print("No members were updated.")
            
        print(f"Summary: {tagged_count} tagged, {skipped_count} skipped (already in the excluded list).")

if __name__ == '__main__':
    tag_members()
