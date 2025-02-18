from rest_framework import serializers
from baggage_registration.models import *
from collections import OrderedDict

class BaggageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Baggage
        fields = ['id', 'number', 'weight', 'description', 'image']

        def get_fields(self):
            new_fields = OrderedDict()
            for name, field in super().get_fields().items():
                field.required = False
                new_fields[name] = field
            return new_fields

class SingleBaggageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Baggage
        fields = ['id', 'number', 'weight', 'description', 'image', 'status']


class CreateUpdateBaggageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Baggage
        fields = ['id', 'number', 'weight', 'description']


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

        def get_fields(self):
            new_fields = OrderedDict()
            for name, field in super().get_fields().items():
                field.required = False
                new_fields[name] = field
            return new_fields


class SingleTransferSerializer(serializers.ModelSerializer):
    baggages = serializers.SerializerMethodField()
    user = serializers.SerializerMethodField()
    moderator = serializers.SerializerMethodField()

    def get_baggages(self, transfer):
        baggage_transfers = BaggageTransfer.objects.filter(transfer=transfer)
        baggages_data = []
        for baggage_transfer in baggage_transfers:
            baggage_data = BaggageSerializer(baggage_transfer.baggage).data
            baggage_data['fragility'] = baggage_transfer.fragility
            baggages_data.append(baggage_data)

        return baggages_data

    def get_user(self, transfer):
        return transfer.user.username

    def get_moderator(self, transfer):
        if transfer.moderator:
            return transfer.moderator.username
        return None

    class Meta:
        model = Transfer
        fields = '__all__'

class BaggageTransferSerializer(serializers.ModelSerializer):
    class Meta:
        model = BaggageTransfer
        fields = '__all__'

        def get_fields(self):
            new_fields = OrderedDict()
            for name, field in super().get_fields().items():
                field.required = False
                new_fields[name] = field
            return new_fields


class UserSerializer(serializers.ModelSerializer):
    is_staff = serializers.BooleanField(default=False, required=False)
    is_superuser = serializers.BooleanField(default=False, required=False)
    class Meta:
        model = User
        fields = ('id', 'email', 'password', 'first_name', 'last_name', 'username', 'is_staff', 'is_superuser')
        extra_kwargs = {"password": {"write_only": True},
                        "is_staff": {"default": False}}


    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data["username"],
            password=validated_data["password"],
            first_name=validated_data["first_name"],
            last_name=validated_data["last_name"],
            email=validated_data.get("email", ""),
            is_staff=validated_data['is_staff'],
            is_superuser=validated_data['is_superuser']
        )
        return user

    def update(self, instance, validated_data):
        print("Received validated data:", validated_data)

        if 'email' in validated_data:
            instance.email = validated_data['email']
        if 'first_name' in validated_data:
            instance.first_name = validated_data['first_name']
        if 'last_name' in validated_data:
            instance.last_name = validated_data['last_name']
        if 'password' in validated_data:
            print("Password from validated_data:", validated_data['password'])
            instance.set_password(validated_data['password'])
        if 'username' in validated_data:
            instance.username = validated_data['username']

        instance.save()
        print("Instance saved successfully with updated data")
        return instance

class UserListSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'is_staff', 'is_superuser']
