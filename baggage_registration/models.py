# models.py
from django.db import models
from django.contrib.auth.models import User
from django.utils.timezone import now

class Baggage(models.Model):
    number = models.CharField(max_length=10, unique=True)
    image = models.URLField(null=True, max_length=80)
    weight = models.IntegerField()
    description = models.TextField()

    STATUS_CHOICES = [
        (True, 'Действует'),
        (False, 'Удален'),
    ]
    status = models.BooleanField(choices=STATUS_CHOICES, default=True)

    def __str__(self):
        return f"Baggage {self.number} (Вес {self.weight} кг)"

class Transfer(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Черновик'),
        ('deleted', 'Удален'),
        ('formed', 'Сформирован'),
        ('completed', 'Завершен'),
        ('rejected', 'Отклонен'),
    ]

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    transfer_date = models.DateField(null=True, auto_now_add=True)
    owner_name = models.CharField(null=True, max_length=50)
    flight = models.CharField(null=True, max_length=10)
    moderator = models.ForeignKey(User, related_name='moderated_transfers', on_delete=models.SET_NULL, null=True)
    user = models.ForeignKey(User, related_name='transfers', on_delete=models.CASCADE)
    creation_date = models.DateField(default=now)
    formation_date = models.DateField(null=True)
    completion_date = models.DateField(null=True)
    heaviest_baggage = models.IntegerField(null=True)
    baggages = models.ManyToManyField(Baggage, through='BaggageTransfer')
    def __str__(self):
        return f'Transfer {self.id} - {self.owner_name} on {self.transfer_date}'

class BaggageTransfer(models.Model):
    transfer = models.ForeignKey(Transfer, related_name='items', on_delete=models.CASCADE)
    baggage = models.ForeignKey(Baggage, related_name='transfers', on_delete=models.CASCADE)
    fragility = models.BooleanField(default=False)

    class Meta:
        unique_together = ('transfer', 'baggage')

    def __str__(self):
        return f"BaggageTransfer (Baggage {self.baggage.id} - Transfer {self.transfer.id}, Fragility {self.fragility})"