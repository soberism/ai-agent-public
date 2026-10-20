from backend.db.cross_system_models import EmailDelivery, MailImport
from backend.db.document_models import DocumentReviewItem
from backend.db.household_models import (
    Contact,
    ContactGroup,
    Household,
    HouseholdProfile,
    Pet,
)
from backend.db.life_models import (
    LifePreference,
    MealPlan,
    MedicalAppointment,
    PantryItem,
)
from backend.db.models import AssistantMemory, CalendarEvent, Checklist, Todo

SOURCES = [
    (
        Todo,
        "todo",
        "title",
        ("title", "description", "due_date", "due_time"),
        "/todos/{id}/edit",
    ),
    (
        CalendarEvent,
        "event",
        "title",
        ("title", "description", "location", "starts_at", "ends_at"),
        "/calendar/{id}/edit",
    ),
    (Checklist, "checklist", "title", ("title",), "/checklists/{id}"),
    (
        Contact,
        "contact",
        "name",
        ("name", "relationship", "phone", "email"),
        "/contacts",
    ),
    (ContactGroup, "contact_group", "name", ("name",), "/contacts"),
    (
        DocumentReviewItem,
        "document_review",
        "title",
        ("title", "evidence"),
        "/document-review",
    ),
    (
        MealPlan,
        "meal",
        "title",
        (
            "title",
            "schedule_text",
            "dish",
            "notes",
            "ingredients",
            "preferences",
            "meal_date",
            "meal_type",
            "diners",
        ),
        "/meals/{id}",
    ),
    (
        MedicalAppointment,
        "appointment",
        "service_type",
        ("patient_name", "provider_name", "service_type", "notes"),
        "/appointments",
    ),
    (PantryItem, "pantry", "name", ("name", "unit", "expires_on"), "/meals/settings"),
    (LifePreference, "preference", "label", ("label",), "/meals/settings"),
    (AssistantMemory, "memory", "content", ("content",), "/assistant/preferences"),
    (MailImport, "mail", "subject", ("subject", "sender", "body"), "/connections"),
    (EmailDelivery, "email", "subject", ("subject", "body"), "/connections"),
    (Household, "household", "name", ("name",), "/family"),
    (HouseholdProfile, "profile", "name", ("name", "relationship"), "/family"),
    (Pet, "pet", "name", ("name", "species", "breed"), "/family"),
]
