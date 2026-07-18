import csv
from pathlib import Path

from app.database import Base, SessionLocal, engine
from app.models import Agent, AgentIntent, Intent

DATASET_PATH = Path("../training/dataset.csv")
FALLBACK_DATASET_PATH = Path(__file__).resolve().parent / "training" / "dataset.csv"

AGENT_SEEDS = [
    {
        "name": "Budi",
        "email": "budi@example.com",
        "role": "support",
        "intents": [
            "complaint",
            "cancellation_request",
            "refund_request",
        ],
    },
    {
        "name": "Siti",
        "email": "siti@example.com",
        "role": "tech",
        "intents": ["technical_support", "account_data"],
    },
    {
        "name": "Rina",
        "email": "rina@example.com",
        "role": "marketing",
        "intents": ["promotions_discounts", "product_service_info"],
    },
    {
        "name": "Adi",
        "email": "adi@example.com",
        "role": "finance",
        "intents": ["payment_inquiry"],
    },
    {
        "name": "Dedi",
        "email": "dedi@example.com",
        "role": "logistik",
        "intents": ["shipping_information", "order_status", "operating_hours_location"],
    },
]


def resolve_dataset_path() -> Path:
    if DATASET_PATH.exists():
        return DATASET_PATH
    if FALLBACK_DATASET_PATH.exists():
        return FALLBACK_DATASET_PATH
    raise FileNotFoundError(
        f"Dataset not found in '{DATASET_PATH}' or '{FALLBACK_DATASET_PATH}'."
    )


def load_unique_intents(csv_path: Path) -> list[str]:
    with csv_path.open("r", encoding="utf-8", newline="") as dataset_file:
        reader = csv.DictReader(dataset_file)
        if not reader.fieldnames or "intent" not in reader.fieldnames:
            raise ValueError("CSV must contain an 'intent' column.")

        unique_intents: list[str] = []
        seen: set[str] = set()
        for row in reader:
            intent_name = (row.get("intent") or "").strip()
            if intent_name and intent_name not in seen:
                seen.add(intent_name)
                unique_intents.append(intent_name)

    if len(unique_intents) < 11:
        raise ValueError(
            f"Expected at least 11 unique intents in dataset, found {len(unique_intents)}."
        )

    return unique_intents[:11]


def main() -> None:
    Base.metadata.create_all(bind=engine)
    dataset_path = resolve_dataset_path()
    session = SessionLocal()

    try:
        intent_names = load_unique_intents(dataset_path)

        mapped_intents = {
            intent_name for agent_seed in AGENT_SEEDS for intent_name in agent_seed["intents"]
        }
        missing_mapped_intents = sorted(mapped_intents.difference(intent_names))
        if missing_mapped_intents:
            missing = ", ".join(missing_mapped_intents)
            raise ValueError(f"Mapped intents not found in dataset unique intents: {missing}")

        session.query(AgentIntent).delete()
        session.query(Agent).delete()
        session.query(Intent).delete()
        session.flush()

        intent_objects = [Intent(name=name) for name in intent_names]
        session.add_all(intent_objects)
        session.flush()

        agent_objects = [
            Agent(name=agent_seed["name"], email=agent_seed["email"], role=agent_seed["role"])
            for agent_seed in AGENT_SEEDS
        ]
        session.add_all(agent_objects)
        session.flush()

        intents_by_name = {intent.name: intent for intent in intent_objects}
        agents_by_email = {agent.email: agent for agent in agent_objects}

        agent_intent_objects: list[AgentIntent] = []
        for agent_seed in AGENT_SEEDS:
            agent = agents_by_email[agent_seed["email"]]
            for intent_name in agent_seed["intents"]:
                intent = intents_by_name[intent_name]
                agent_intent_objects.append(
                    AgentIntent(agent_id=agent.id, intent_id=intent.id)
                )

        session.add_all(agent_intent_objects)
        session.commit()

        print("Seed completed successfully.")
        print(f"Dataset source: {dataset_path}")
        print(f"Intents seeded: {len(intent_objects)}")
        print(f"Agents seeded: {len(agent_objects)}")
        print(f"Agent-intent mappings seeded: {len(agent_intent_objects)}")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
