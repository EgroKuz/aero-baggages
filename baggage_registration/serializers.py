from rest_framework import serializers
from baggage_registration.models import *

class BaggageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Baggage
        fields = ['id', 'number', 'weight', 'description', 'image']

class TransferSerializer(serializers.ModelSerializer):
    user = serializers.SerializerMethodField()
    moderator = serializers.SerializerMethodField()

    def get_baggages(self, transfer):
        baggage_transfer = BaggageTransfer.objects.filter(transfer=transfer)
        baggages = [baggage_transfer.baggage for baggage_transfer in baggage_transfer]
        serializer = BaggageSerializer(baggages, many=True)
        return serializer.data

    def get_user(self, transfer):
        return transfer.user.username

    def get_moderator(self, transfer):
        if transfer.moderator:
            return transfer.moderator.username
        return None

    class Meta:
        model = Transfer
        fields = ['id', 'transfer_date', 'owner_name', 'flight', 'user', 'moderator', 'status', 'creation_date', 'formation_date', 'completion_date', 'heaviest_baggage']

class BaggageTransferSerializer(serializers.ModelSerializer):
    class Meta:
        model = BaggageTransfer
        fields = '__all__'

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'username', 'password', 'first_name', 'last_name', 'email', 'date_joined')

class UserRegisterSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'username', 'password', 'first_name', 'last_name', 'email')
        write_only_fields = ('password',)
        read_only_fields = ('id',)

    def create(self, validated_data):
        user = User.objects.create(
            username=validated_data['username'],
            first_name=validated_data['first_name'],
            last_name=validated_data['last_name'],
            email=validated_data['email'],
        )

        user.set_password(validated_data['password'])
        user.save()
        return user

class UserLoginSerializer(serializers.Serializer):
    username = serializers.CharField(required=True)
    password = serializers.CharField(required=True)