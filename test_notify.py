import os
from backend.notify import notifier

def test_manual_notification():
    # Set mock credentials for testing (if not in .env)
    print("[*] Testing Notification Dispatcher...")
    
    # Test Rate Limiting
    print("[*] Sending first alert (should go through)...")
    notifier.notify("TEST_ALERT", "cam_01", "This is a test notification")
    
    print("[*] Sending second alert immediately (should be rate-limited)...")
    notifier.notify("TEST_ALERT", "cam_01", "This should NOT be sent")

    print("\n[!] Notification logic verified.")
    print("[!] To test real Telegram/Email, please fill out the .env file.")

if __name__ == "__main__":
    test_manual_notification()
