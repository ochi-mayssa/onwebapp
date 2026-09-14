from platform_app.models import IoTDevice, SocialAccount, SecurityAudit
import random

def run():
    print("Seeding Platform Data...")

    # Clear existing data
    IoTDevice.objects.all().delete()
    SocialAccount.objects.all().delete()
    SecurityAudit.objects.all().delete()

    # IoT Devices
    devices = [
        {'name': 'Temperature Sensor A1', 'id': 'TEMP-001', 'loc': 'Warehouse 1'},
        {'name': 'Pressure Gauge B2', 'id': 'PRES-002', 'loc': 'Factory Floor'},
        {'name': 'Conveyor Belt Motor', 'id': 'MOTO-003', 'loc': 'Assembly Line'},
        {'name': 'Humidity Sensor C3', 'id': 'HUMI-004', 'loc': 'Storage'},
        {'name': 'Smart Camera D4', 'id': 'CAM-005', 'loc': 'Entrance'},
        {'name': 'Robot Arm E5', 'id': 'ROBO-006', 'loc': 'Assembly Line'},
    ]
    
    for d in devices:
        IoTDevice.objects.create(
            name=d['name'],
            device_id=d['id'],
            location=d['loc'],
            status=random.choice(['active', 'active', 'active', 'inactive'])
        )
    print(f"Created {len(devices)} IoT Devices")

    # Social Accounts
    accounts = [
        {'platform': 'twitter', 'username': '@IndustrialCo', 'followers': 12500},
        {'platform': 'linkedin', 'username': 'Industrial-Company-Inc', 'followers': 8400},
        {'platform': 'facebook', 'username': 'IndustrialCoPage', 'followers': 5600},
        {'platform': 'instagram', 'username': 'industrial_co_life', 'followers': 3200},
    ]

    for a in accounts:
        SocialAccount.objects.create(
            platform=a['platform'],
            username=a['username'],
            followers_count=a['followers'],
            is_active=True
        )
    print(f"Created {len(accounts)} Social Accounts")

    # Security Audit
    SecurityAudit.objects.create(
        score=98,
        status='System Secure. No vulnerabilities found.'
    )
    print("Created Security Audit")

    print("Seeding Complete.")
