import html
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Business, Equipment, Policy, PolicyEquipment


def generate_policy_html(
    policy_number: str,
    business_name: str,
    equipment_description: str,
    start_date: str,
    end_date: str,
    premium_amount: str,
    deductible_amount: str,
    coverage_limit: str,
) -> str:
    escaped_policy_number = html.escape(str(policy_number))
    escaped_business_name = html.escape(str(business_name))
    escaped_equipment = html.escape(str(equipment_description))
    escaped_start = html.escape(str(start_date))
    escaped_end = html.escape(str(end_date))
    escaped_premium = html.escape(str(premium_amount))
    escaped_deductible = html.escape(str(deductible_amount))
    escaped_coverage = html.escape(str(coverage_limit))

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Policy {escaped_policy_number}</title>
</head>
<body>
    <h1>EquipSure Policy Certificate</h1>
    <p>Simulated policy for demonstration only</p>
    <div class="policy-details">
        <p><strong>Policy Number:</strong> {escaped_policy_number}</p>
        <p><strong>Business Name:</strong> {escaped_business_name}</p>
        <p><strong>Equipment Description:</strong> {escaped_equipment}</p>
        <p><strong>Coverage Period:</strong> {escaped_start} to {escaped_end}</p>
        <p><strong>Premium:</strong> {escaped_premium}</p>
        <p><strong>Deductible:</strong> {escaped_deductible}</p>
        <p><strong>Coverage Limit:</strong> {escaped_coverage}</p>
    </div>
    <p>Policy issued by EquipSure (simulated)</p>
</body>
</html>"""


def build_policy_document_html(session: Session, policy: Policy) -> str:
    business = session.get(Business, policy.business_id)
    business_name = business.name if business else "Unknown Business"

    equipment_items = session.execute(
        select(Equipment)
        .join(PolicyEquipment, PolicyEquipment.equipment_id == Equipment.id)
        .where(PolicyEquipment.policy_id == policy.id)
    ).scalars().all()

    if equipment_items:
        equipment_description = ", ".join(e.description for e in equipment_items)
    else:
        equipment_description = "None"

    return generate_policy_html(
        policy_number=policy.policy_number,
        business_name=business_name,
        equipment_description=equipment_description,
        start_date=str(policy.start_date),
        end_date=str(policy.end_date),
        premium_amount=str(policy.premium_amount),
        deductible_amount=str(policy.deductible_amount),
        coverage_limit=str(policy.coverage_limit),
    )

