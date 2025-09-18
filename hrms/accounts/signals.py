from django.db.models.signals import post_delete
from django.dispatch import receiver
from .models import HR, Employee, CEO, Manager, Admin, Attendance, Leave, User

@receiver(post_delete, sender=HR)
@receiver(post_delete, sender=Employee)
@receiver(post_delete, sender=CEO)
@receiver(post_delete, sender=Manager)
@receiver(post_delete, sender=Admin)
@receiver(post_delete, sender=Attendance)
@receiver(post_delete, sender=Leave)
def delete_user_on_child_delete(sender, instance, **kwargs):
    try:
        user = instance.email
        user.delete()
        print(f"[Signal] Deleted User {user.email} because {sender.__name__} row was deleted.")
    except Exception as e:
        print(f"[Signal ERROR] Failed to delete User: {e}")
