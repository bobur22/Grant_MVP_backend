import logging
import random

import boto3
from celery import shared_task
from config.celery import app
from django.conf import settings
from eskiz_sms import EskizSMS

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def send_sms_task(self, phone_number, code):

    try:
        eskiz = EskizSMS(email=settings.ESKIZ_EMAIL, password=settings.ESKIZ_PASSWORD)

        message = f"Your verification code is: {code}. Valid for 5 minutes."

        response = eskiz.send_sms(
            phone_number,
            message=message,
            from_whom="4546"
        )

        logger.info(f"✅ SMS sent successfully to {phone_number}: {response}")
        return response

    except Exception as exc:
        logger.error(f"❌ Failed to send SMS to {phone_number}: {exc}")
        raise self.retry(exc=exc, countdown=5)

# @shared_task(bind=True, max_retries=3)
# def send_sms_task(self, phone_number, code):
#     """
#     Send SMS using AWS SNS (Amazon Simple Notification Service).
#     """
#     try:
#         sns = boto3.client(
#             "sns",
#             aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
#             aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
#             region_name=settings.AWS_REGION
#         )
#
#         message = f"Your verification code is: {code}. Valid for 5 minutes."
#
#         response = sns.publish(
#             PhoneNumber=phone_number,
#             Message=message
#         )
#
#         logger.info(f"✅ SMS sent successfully to {phone_number} (MessageId: {response['MessageId']})")
#         return response["MessageId"]
#
#     except Exception as exc:
#         logger.error(f"❌ Failed to send SMS to {phone_number}: {exc}")
#         raise self.retry(exc=exc, countdown=5)


"""
Important

#Bobur will add twilio. now i even could not register on twilio, i've created 3 new account but didn't get phone number
# confirmation code

"""
@app.task
def send_reset_code(phone_number, code):
    return random.randint(100000, 999999)

# @shared_task(bind=True, max_retries=3)
# def send_sms_task_twilio(self, phone_number, code):
#     try:
#         from twilio.rest import Client
#
#         client = Client(
#             settings.TWILIO_ACCOUNT_SID,
#             settings.TWILIO_AUTH_TOKEN
#         )
#
#         message = client.messages.create(
#             body=f"Your verification code is: {code}. Valid for 5 minutes.",
#             from_=settings.TWILIO_PHONE_NUMBER,  # Your Twilio phone number
#             to=phone_number
#         )
#
#         logger.info(f"✅ SMS sent successfully to {phone_number} (SID: {message.sid})")
#         return message.sid
#
#     except Exception as exc:
#         logger.error(f"❌ Twilio SMS failed to {phone_number}: {exc}")
#         raise self.retry(exc=exc, countdown=60)
