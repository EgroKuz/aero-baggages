from rest_framework.response import Response
from rest_framework import status
from .serializers import *
from django.db import connection
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.views import APIView
from rest_framework.decorators import api_view
from django.db.models import Max
from .minio import *
from django.contrib.auth import authenticate


def get_user():
    return User.objects.filter(is_superuser=False).first()

def get_moderator():
    return User.objects.filter(is_superuser=True).first()


@api_view(['GET'])
def get_baggages_list(request):
    baggage_weight = request.GET.get('baggage_weight', '')

    baggages = Baggage.objects.filter(status=True).filter(weight__istartswith=baggage_weight)

    serializer = BaggageSerializer(baggages, many=True)

    draft_transfer = Transfer.objects.filter(status='draft').first()

    response = {
        'baggages': serializer.data,
        'draft_transfer': draft_transfer.id if draft_transfer else None,
        'baggages_to_transfer': len(draft_transfer.baggages.all()) if draft_transfer else None,
    }
    return Response(response, status=status.HTTP_200_OK)

@api_view(['GET'])
def get_baggage_by_id(request, baggage_id):
    try:
        baggage = Baggage.objects.get(pk=baggage_id)
    except Baggage.DoesNotExist:
        return Response({'error': 'Багаж не найден!'}, status=status.HTTP_404_NOT_FOUND)

    serializer = BaggageSerializer(baggage, many=False)
    return Response(serializer.data)

@api_view(['POST'])
def create_baggage(request):
    baggages_data = request.data.copy()
    baggages_data.pop('image', None)
    serializer = BaggageSerializer(data=baggages_data)
    serializer.is_valid(raise_exception=True)

    new_baggage = serializer.save()
    return Response(BaggageSerializer(new_baggage).data, status=status.HTTP_201_CREATED)

@api_view(['PUT'])
def update_baggage(request, baggage_id):
    try:
        baggage = Baggage.objects.get(pk=baggage_id)
    except Baggage.DoesNotExist:
        return Response({'error': 'Багаж не найден'}, status=status.HTTP_404_NOT_FOUND)

    baggage_data = request.data.copy()
    baggage_data.pop('image', None)

    serializer = BaggageSerializer(baggage, data=baggage_data, partial=True)
    serializer.is_valid(raise_exception=True)
    updated_baggage = serializer.save()

    pic = request.FILES.get('image')
    if pic:
        pic_result = add_pic(updated_baggage, pic)
        if 'error' in pic_result.data:
            return pic_result

    return Response(BaggageSerializer(updated_baggage).data, status=status.HTTP_200_OK)

@api_view(['DELETE'])
def delete_baggage(request, baggage_id):
    try:
        baggage = Baggage.objects.get(pk=baggage_id)
    except Baggage.DoesNotExist:
        return Response({'error': 'Багаж не найден'}, status=status.HTTP_404_NOT_FOUND)

    baggage.status = False
    baggage.save()

    baggages = Baggage.objects.filter(status=True)
    serializer = BaggageSerializer(baggages, many=True)
    return Response(serializer.data)

@api_view(["POST"])
def update_baggage_image(request, baggage_id):
    try:
        baggage = Baggage.objects.get(pk=baggage_id)
    except Baggage.DoesNotExist:
        return Response({"Ошибка": "Орбита не найдена"}, status=status.HTTP_404_NOT_FOUND)

    image = request.FILES.get("image")

    if image is not None:
        pic_result = add_pic(baggage, image)
        if 'error' in pic_result.data:
            return pic_result

        serializer = BaggageSerializer(baggage)
        return Response(serializer.data, status=status.HTTP_200_OK)

    return Response({"error": "Изображение не предоставлено"}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
def add_baggage_to_transfer(request, baggage_id):
    try:
        baggage = Baggage.objects.get(pk=baggage_id)
    except Baggage.DoesNotExist:
        return Response({'error': 'Багаж не найден'}, status=status.HTTP_404_NOT_FOUND)

    draft_transfer = Transfer.objects.filter(status='draft').first()

    if draft_transfer is None:
        draft_transfer = Transfer.objects.create(
            creation_date=timezone.now().date(),
            user=User.objects.filter(is_superuser=False).first()
        )
        draft_transfer.save()

    if BaggageTransfer.objects.filter(transfer=draft_transfer, baggage=baggage).exists():
        return Response({'error': 'Багаж уже добавлен в перемещение'}, status=status.HTTP_405_METHOD_NOT_ALLOWED)

    try:
        baggage_transfer = BaggageTransfer.objects.create(
            transfer=draft_transfer,
            baggage=baggage,
            fragility=False,
        )
    except Exception as e:
        return Response({'error': f'Ошибка при создании связи: {str(e)}'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    serializer = TransferSerializer(draft_transfer)
    return Response(serializer.get_baggages(draft_transfer), status=status.HTTP_200_OK)

@api_view(["GET"])
def get_transfers_list(request):
    status = request.GET.get("status", '')
    date_formation_start = request.GET.get("date_formation_start")
    date_formation_end = request.GET.get("date_formation_end")

    transfers = Transfer.objects.exclude(status__in=['draft', 'deleted'])

    if status in ['formed', 'completed', 'rejected']:
        transfers = transfers.filter(status=status)

    if date_formation_start and parse_datetime(date_formation_start):
        transfers = transfers.filter(transfer_date__gte=parse_datetime(date_formation_start))

    if date_formation_end and parse_datetime(date_formation_end):
        transfers = transfers.filter(transfer_date__lt=parse_datetime(date_formation_end))

    serializer = TransferSerializer(transfers, many=True)

    return Response(serializer.data)

@api_view(["GET"])
def get_transfer_by_id(request, transfer_id):
    try:
        transfer = Transfer.objects.get(pk=transfer_id)
    except Transfer.DoesNotExist:
        return Response({"error": "Заявка не найдена"}, status=status.HTTP_404_NOT_FOUND)

    serializer = TransferSerializer(transfer, many=False)

    return Response(serializer.data)

@api_view(["PUT"])
def update_transfer(request, transfer_id):
    try:
        transfer = Transfer.objects.get(pk=transfer_id)
    except Transfer.DoesNotExist:
        return Response({"error": "Заявка не найдена"}, status=status.HTTP_404_NOT_FOUND)

    allowed_fields = ['transfer_date', 'owner_name', 'flight']

    data = {key: value for key, value in request.data.items() if key in allowed_fields}

    if not data:
        return Response({"error": "Нет данных для обновления или поля не разрешены"},
                        status=status.HTTP_400_BAD_REQUEST)

    serializer = TransferSerializer(transfer, data=data, partial=True)

    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(["PUT"])
def update_status_user(request, transfer_id):
    try:
        transfer = Transfer.objects.get(pk=transfer_id)
    except Transfer.DoesNotExist:
        return Response({"error": "Заявка не найдена"}, status=status.HTTP_404_NOT_FOUND)

    if transfer.status != 'draft':
        return Response({"error": "Заявку нельзя изменить, так как она не в статусе 'Черновик'"},
                        status=status.HTTP_405_METHOD_NOT_ALLOWED)

    required_fields = ['transfer_date', 'owner_name', 'flight']

    missing_fields = [field for field in required_fields if not getattr(transfer, field)]

    if missing_fields:
        return Response(
            {"error": f"Не заполнены обязательные поля: {', '.join(missing_fields)}"},
            status=status.HTTP_400_BAD_REQUEST
        )

    transfer.status = 'formed'
    transfer.formation_date = timezone.now().date()
    transfer.save()

    serializer = TransferSerializer(transfer, many=False)
    return Response(serializer.data, status=status.HTTP_200_OK)

@api_view(["PUT"])
def update_status_admin(request, transfer_id):
    try:
        transfer = Transfer.objects.get(pk=transfer_id)
    except Transfer.DoesNotExist:
        return Response({"error": "Заявка не найдена"}, status=status.HTTP_404_NOT_FOUND)

    request_status = request.data["status"]

    if request_status not in ['completed', 'rejected']:
        return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)

    if transfer.status != 'formed':
        return Response({'error': "Заявка ещё не сформирована"}, status=status.HTTP_405_METHOD_NOT_ALLOWED)

    transfer.status = request_status
    transfer.moderator = get_moderator()
    transfer.heaviest_baggage = transfer.baggages.aggregate(max_weight=Max('weight'))['max_weight']
    transfer.completion_date = timezone.now().date()
    transfer.save()

    serializer = TransferSerializer(transfer, many=False)

    return Response(serializer.data)

@api_view(["DELETE"])
def delete_transfer(request, transfer_id):
    try:
        transfer = Transfer.objects.get(pk=transfer_id)
    except Transfer.DoesNotExist:
        return Response({"error": "Заявка не найдена"}, status=status.HTTP_404_NOT_FOUND)

    if transfer.status != 'draft':
        return Response({'error': 'Нельзя удалить данную заявку'}, status=status.HTTP_405_METHOD_NOT_ALLOWED)

    transfer.status = 'deleted'
    transfer.save()
    serializer = TransferSerializer(transfer, many=False)

    return Response(serializer.data)


@api_view(["DELETE"])
def delete_baggage_from_transfer(request, baggage_id, transfer_id):
    try:
        baggage_transfer = BaggageTransfer.objects.get(baggage_id=baggage_id, transfer_id=transfer_id)
    except BaggageTransfer.DoesNotExist:
        return Response({"error": "Связь между багажом и заявкой не найдена"}, status=status.HTTP_404_NOT_FOUND)

    baggage_transfer.delete()

    try:
        transfer = Transfer.objects.get(pk=transfer_id)
    except Transfer.DoesNotExist:
        return Response({"error": "Заявка не найдена после удаления багажа"}, status=status.HTTP_404_NOT_FOUND)

    serializer = TransferSerializer(transfer, many=False)

    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(["PUT"])
def update_baggage_transfer(request, baggage_id, transfer_id):
    try:
        baggage_transfer = BaggageTransfer.objects.get(baggage_id=baggage_id, transfer_id=transfer_id)
    except BaggageTransfer.DoesNotExist:
        return Response({"error": "Связь между багажом и заявкой не найдена"}, status=status.HTTP_404_NOT_FOUND)

    # Меняем хрупкость для текущего baggage_transfer
    baggage_transfer.fragility = not baggage_transfer.fragility
    baggage_transfer.save()

    # Возвращаем обновлённые данные
    serializer = BaggageTransferSerializer(baggage_transfer)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(["POST"])
def register(request):
    serializer = UserRegisterSerializer(data=request.data)

    if not serializer.is_valid():
        return Response({"error": "Некорректные данные"}, status=status.HTTP_400_BAD_REQUEST)

    user = serializer.save()

    serializer = UserSerializer(user)
    return Response(serializer.data, status=status.HTTP_201_CREATED)


@api_view(["PUT"])
def update_user(request, user_id):
    if not User.objects.filter(pk=user_id).exists():
        return Response(status=status.HTTP_404_NOT_FOUND)

    user = User.objects.get(pk=user_id)
    serializer = UserSerializer(user, data=request.data, many=False, partial=True)

    if not serializer.is_valid():
        return Response(status=status.HTTP_409_CONFLICT)

    serializer.save()

    return Response(serializer.data)


@api_view(["POST"])
def login(request):
    serializer = UserLoginSerializer(data=request.data)

    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_401_UNAUTHORIZED)

    user = authenticate(**serializer.data)
    if user is None:
        return Response(status=status.HTTP_401_UNAUTHORIZED)

    return Response(status=status.HTTP_200_OK)


@api_view(["POST"])
def logout(request):
    return Response(status=status.HTTP_200_OK)