import os
import datetime
from sqlalchemy.orm import Session
from .models import Member, Responder


def seed_database(db: Session, force: bool = False) -> bool:
    """
    Phase 6: Explicit, optional demo seeding.
    Production startup NEVER silently recreates demo people or overwrites user-entered records.
    Only runs if force=True or ENABLE_DEMO_SEED=true is explicitly set, and only when tables are empty.
    """
    enable_demo = force or (os.environ.get("ENABLE_DEMO_SEED", "false").lower() in ("true", "1", "yes"))
    if not enable_demo:
        return False

    if db.query(Member).count() > 0:
        return False

    now = datetime.datetime.utcnow()

    # 1. Explicit Demo Family Members (marked is_demo=True)
    members = [
        Member(
            name="Eleanor Vance (Grandmother)",
            relationship="Grandmother",
            age=74,
            phone="+91 98765 23456",
            blood_group="O+",
            medical_notes="Hypertension, mild osteoporosis, pacemaker installed 2023.",
            emergency_contact_name="Marcus Vance (Son)",
            emergency_contact_phone="+91 98765 87654",
            is_active=True,
            is_demo=True,
            created_at=now,
            updated_at=now
        ),
        Member(
            name="Marcus Vance",
            relationship="Father",
            age=46,
            phone="+91 98765 87654",
            blood_group="A+",
            medical_notes="No known drug allergies.",
            emergency_contact_name="Sarah Vance (Spouse)",
            emergency_contact_phone="+91 98765 34567",
            is_active=True,
            is_demo=True,
            created_at=now,
            updated_at=now
        ),
        Member(
            name="Sarah Vance",
            relationship="Mother",
            age=43,
            phone="+91 98765 34567",
            blood_group="B+",
            medical_notes="Asthma inhaler prescribed (Albuterol).",
            emergency_contact_name="Marcus Vance",
            emergency_contact_phone="+91 98765 87654",
            is_active=True,
            is_demo=True,
            created_at=now,
            updated_at=now
        ),
        Member(
            name="Leo Vance",
            relationship="Son",
            age=12,
            phone="+91 98765 45678",
            blood_group="O+",
            medical_notes="Peanut allergy (Carries EpiPen).",
            emergency_contact_name="Sarah Vance",
            emergency_contact_phone="+91 98765 34567",
            is_active=True,
            is_demo=True,
            created_at=now,
            updated_at=now
        ),
    ]
    db.add_all(members)
    db.commit()

    # 2. Explicit Demo Responders (marked is_demo=True, location_source="demo_seed")
    responders = [
        Responder(
            name="Officer David Miller",
            role="Neighborhood Patrol",
            organization="Community Safety Patrol",
            phone="+91 98765 90112",
            latitude=37.7760,
            longitude=-122.4210,
            location_source="demo_seed",
            location_updated_at=now,
            is_available=True,
            is_active=True,
            is_demo=True,
            skills="CPR, First Aid, AED Equipped",
            created_at=now,
            updated_at=now
        ),
        Responder(
            name="Dr. Karen Lee (Neighbor)",
            role="Registered Nurse / Neighbor",
            organization="Neighborhood Medical Volunteer",
            phone="+91 98765 90233",
            latitude=37.7735,
            longitude=-122.4170,
            location_source="demo_seed",
            location_updated_at=now,
            is_available=True,
            is_active=True,
            is_demo=True,
            skills="Advanced Life Support, Pediatric Care",
            created_at=now,
            updated_at=now
        ),
        Responder(
            name="Metro Station 4 Paramedic Unit",
            role="Emergency Paramedic Squad",
            organization="Metro EMS",
            phone="+91 98765 90355",
            latitude=37.7810,
            longitude=-122.4100,
            location_source="demo_seed",
            location_updated_at=now,
            is_available=True,
            is_active=True,
            is_demo=True,
            skills="Full Paramedic Equipment, Trauma Care",
            created_at=now,
            updated_at=now
        ),
        Responder(
            name="St. Jude Urgent Care Facility",
            role="Nearby Medical Center",
            organization="St. Jude Health Network",
            phone="+91 98765 90477",
            latitude=37.7680,
            longitude=-122.4300,
            location_source="demo_seed",
            location_updated_at=now,
            is_available=True,
            is_active=True,
            is_demo=True,
            skills="24/7 Triage, Emergency Room",
            created_at=now,
            updated_at=now
        ),
        Responder(
            name="Volunteer James Foster",
            role="Community Volunteer",
            organization="CERT Volunteer Corps",
            phone="+91 98765 90599",
            latitude=37.7790,
            longitude=-122.4250,
            location_source="demo_seed",
            location_updated_at=now,
            is_available=False,
            is_active=True,
            is_demo=True,
            skills="Basic First Aid",
            created_at=now,
            updated_at=now
        )
    ]
    db.add_all(responders)
    db.commit()
    print("[Seed Data] Explicit demo family profiles and responders initialized (ENABLE_DEMO_SEED=true).")
