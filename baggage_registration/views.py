from rest_framework.response import Response
from rest_framework import status
from .serializers import *
from django.db import connection
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.views import APIView
from django.db.models import Max
from .minio import *
from django.contrib.auth import authenticate
from .models import *
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from django.db.models import Max
from django.contrib.auth import authenticate
from drf_yasg.utils import swagger_auto_schema
from rest_framework import viewsets
from django.contrib.auth import authenticate, login, logout
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework.permissions import AllowAny
from .authorization import *
from drf_yasg.utils import swagger_auto_schema
from .redis import session_storage
from rest_framework.parsers import FormParser, MultiPartParser
import uuid
from drf_yasg import openapi
from rest_framework.decorators import (
    api_view,
    permission_classes,
    authentication_classes,
    parser_classes,
)


@swagger_auto_schema(
    method="get",
    manual_parameters=[
        openapi.Parameter(
            "baggage_weight",
            openapi.IN_QUERY,
            description="Фильтрация по совпадению веса багажа",
            type=openapi.TYPE_STRING,
        ),
    ],
    responses={
        status.HTTP_200_OK: openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "baggage": openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(type=openapi.TYPE_OBJECT),
                    description="Список найденных багажей",
                ),
                "draft_transfer": openapi.Schema(
                    type=openapi.TYPE_NUMBER,
                    description="ID черновика заявки, если существует",
                    nullable=True,
                ),
            },
        ),
        status.HTTP_400_BAD_REQUEST: "Неверный запрос",
        status.HTTP_403_FORBIDDEN: "Доступ запрещен",
    },
)


@api_view(['GET'])
@permission_classes([AllowAny])
@authentication_classes([AuthBySessionIDIfExists])
def get_baggages_list(request):
    baggage_weight = request.GET.get('baggage_weight', '')

    baggages = Baggage.objects.filter(status=True).filter(weight__istartswith=baggage_weight)

    serializer = BaggageSerializer(baggages, many=True)

    draft_transfer = None
    baggages_to_transfer = None
    if request.user and request.user.is_authenticated:
        try:
            draft_transfer = Transfer.objects.filter(status='draft', user=request.user).first()
            baggages_to_transfer = len(draft_transfer.baggages.all()) if draft_transfer else None
        except Transfer.DoesNotExist:
            draft_transfer = None

    response = {
        'baggages': serializer.data,
        'draft_transfer': draft_transfer.id if draft_transfer else None,
        'baggages_to_transfer': baggages_to_transfer
    }
    return Response(response, status=status.HTTP_200_OK)

@swagger_auto_schema(
    method="get",
    manual_parameters=[
        openapi.Parameter(
            name="baggage_id",
            in_=openapi.IN_PATH,
            type=openapi.TYPE_INTEGER,
            description="ID искомого багажа"
        )
    ],
    responses={
        status.HTTP_200_OK: SingleBaggageSerializer(),
        status.HTTP_404_NOT_FOUND: "Багаж не найден",
    },
)

@api_view(['GET'])
@permission_classes([AllowAny])
def get_baggage_by_id(request, baggage_id):
    try:
        baggage = Baggage.objects.get(pk=baggage_id)
    except Baggage.DoesNotExist:
        return Response({'error': 'Багаж не найден!'}, status=status.HTTP_404_NOT_FOUND)

    serializer = BaggageSerializer(baggage, many=False)
    return Response(serializer.data)

@swagger_auto_schema(
    method="post",
    request_body=CreateUpdateBaggageSerializer,
    responses={
        status.HTTP_201_CREATED: BaggageSerializer(),
        status.HTTP_400_BAD_REQUEST: "Неверные данные",
        status.HTTP_403_FORBIDDEN: "Вы не вошли в систему как модератор",
    },
)

@api_view(['POST'])
def create_baggage(request):
    baggages_data = request.data.copy()
    baggages_data.pop('image', None)
    serializer = BaggageSerializer(data=baggages_data)
    serializer.is_valid(raise_exception=True)

    new_baggage = serializer.save()
    return Response(BaggageSerializer(new_baggage).data, status=status.HTTP_201_CREATED)

@swagger_auto_schema(
    method="put",
    request_body=CreateUpdateBaggageSerializer,
    manual_parameters=[
        openapi.Parameter(
            name="baggage_id",
            in_=openapi.IN_PATH,
            type=openapi.TYPE_INTEGER,
            description="ID обновляемого багажа"
        )
    ],
    responses={
        status.HTTP_200_OK: BaggageSerializer(),
        status.HTTP_403_FORBIDDEN: "Вы не вошли в систему как модератор",
        status.HTTP_404_NOT_FOUND: "Багаж не найден",
        status.HTTP_400_BAD_REQUEST: "Неверные данные",
    },
)

@api_view(['PUT'])
@permission_classes([IsManagerAuth])
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

    return Response(BaggageSerializer(updated_baggage).data, status=status.HTTP_200_OK)

@swagger_auto_schema(
    method="delete",
    manual_parameters=[
        openapi.Parameter(
            name="baggage_id",
            in_=openapi.IN_PATH,
            type=openapi.TYPE_INTEGER,
            description="ID удаляемого багажа"
        )
    ],
    responses={
        status.HTTP_200_OK: BaggageSerializer(many=True),
        status.HTTP_403_FORBIDDEN: "Вы не вошли в систему как модератор",
        status.HTTP_404_NOT_FOUND: "Багаж не найден",
    },
)

@api_view(['DELETE'])
@permission_classes([IsManagerAuth])
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

@swagger_auto_schema(
    method="post",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            "image": openapi.Schema(type=openapi.TYPE_FILE, description="Новое изображение для багажа"),
        },
        required=["image"]
    ),
    manual_parameters=[
        openapi.Parameter(
            name="baggage_id",
            in_=openapi.IN_PATH,
            type=openapi.TYPE_INTEGER,
            description="ID багажа, для которого загружается/изменяется изображение"
        )
    ],
    responses={
        status.HTTP_200_OK: BaggageSerializer(),
        status.HTTP_400_BAD_REQUEST: "Изображение не предоставлено",
        status.HTTP_403_FORBIDDEN: "Вы не вошли в систему как модератор",
        status.HTTP_404_NOT_FOUND: "Багаж не найден",
    },
)

@api_view(["POST"])
@permission_classes([IsManagerAuth])
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

@swagger_auto_schema(
    method="post",
    manual_parameters=[
        openapi.Parameter(
            name="baggage_id",
            in_=openapi.IN_PATH,
            type=openapi.TYPE_INTEGER,
            description="ID багажа, добавляемого в заявку"
        )
    ],
    responses={
        status.HTTP_201_CREATED: TransferSerializer(),
        status.HTTP_404_NOT_FOUND: "Багаж не найден",
        status.HTTP_400_BAD_REQUEST: "Багаж уже добавлен в черновик",
        status.HTTP_403_FORBIDDEN: "Вы не вошли в систему",
        status.HTTP_500_INTERNAL_SERVER_ERROR: "Ошибка при создании связки",
    },
)

@api_view(['POST'])
@permission_classes([IsAuth])
@authentication_classes([AuthBySessionID])
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

@swagger_auto_schema(
    method="get",
    manual_parameters=[
        openapi.Parameter(
            name="status",
            in_=openapi.IN_QUERY,
            type=openapi.TYPE_STRING,
            description="Фильтр по статусу заявки",
        ),
        openapi.Parameter(
            name="date_formation_start",
            in_=openapi.IN_QUERY,
            type=openapi.TYPE_STRING,
            format=openapi.FORMAT_DATETIME,
            description="Начальная дата формирования (формат: YYYY-MM-DDTHH:MM:SS)",
        ),
        openapi.Parameter(
            name="date_formation_end",
            in_=openapi.IN_QUERY,
            type=openapi.TYPE_STRING,
            format=openapi.FORMAT_DATETIME,
            description="Конечная дата формирования (формат: YYYY-MM-DDTHH:MM:SS)",
        ),
    ],
    responses={
        status.HTTP_200_OK: TransferSerializer(many=True),
        status.HTTP_400_BAD_REQUEST: "Некорректный запрос",
        status.HTTP_403_FORBIDDEN: "Вы не вошли в систему",
    },
)

@api_view(["GET"])
@permission_classes([IsAuth])
@authentication_classes([AuthBySessionID])
def get_transfers_list(request):
    status = request.GET.get("status", '')
    date_formation_start = request.GET.get("date_formation_start")
    date_formation_end = request.GET.get("date_formation_end")

    transfers = Transfer.objects.exclude(status__in=['draft', 'deleted'])

    if not request.user.is_superuser:
        transfers = transfers.filter(user=request.user)

    if status in ['formed', 'completed', 'rejected']:
        transfers = transfers.filter(status=status)

    if date_formation_start and parse_datetime(date_formation_start):
        transfers = transfers.filter(transfer_date__gte=parse_datetime(date_formation_start))

    if date_formation_end and parse_datetime(date_formation_end):
        transfers = transfers.filter(transfer_date__lt=parse_datetime(date_formation_end))

    serializer = TransferSerializer(transfers, many=True)

    return Response(serializer.data)

@swagger_auto_schema(
    method="get",
    manual_parameters=[
        openapi.Parameter(
            name="transfer_id",
            in_=openapi.IN_PATH,
            type=openapi.TYPE_INTEGER,
            description="ID искомой заявки",
        ),
    ],
    responses={
        status.HTTP_200_OK: SingleTransferSerializer(),
        status.HTTP_403_FORBIDDEN: "Вы не вошли в систему",
        status.HTTP_404_NOT_FOUND: "Заявка не найдена",
    },
)

@api_view(["GET"])
@permission_classes([IsAuth])
@authentication_classes([AuthBySessionID])
def get_transfer_by_id(request, transfer_id):
    try:
        transfer = Transfer.objects.get(pk=transfer_id)
    except Transfer.DoesNotExist:
        return Response({"error": "Заявка не найдена"}, status=status.HTTP_404_NOT_FOUND)

    serializer = SingleTransferSerializer(transfer, many=False)

    return Response(serializer.data)


@swagger_auto_schema(
    method="put",
    manual_parameters=[
        openapi.Parameter(
            name="transfer_id",
            in_=openapi.IN_PATH,
            type=openapi.TYPE_INTEGER,
            description="ID изменяемой заявки",
        )
    ],
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            "transfer_date": openapi.Schema(
                type=openapi.TYPE_STRING,
                format=openapi.FORMAT_DATETIME,
                description="Дата отправки (формат: YYYY-MM-DDTHH:MM:SS)",
            ),
            "owner_name": openapi.Schema(
                type=openapi.TYPE_STRING,
                description="ФИО владельца багажа",
            ),
            "flight": openapi.Schema(
                type=openapi.TYPE_STRING,
                description="Номер рейса",
            ),
        },
    ),
    responses={
        status.HTTP_200_OK: TransferSerializer(),
        status.HTTP_400_BAD_REQUEST: "Нет данных для обновления или поля не разрешены",
        status.HTTP_403_FORBIDDEN: "Доступ запрещен",
        status.HTTP_404_NOT_FOUND: "Заявка не найдена",
    },
)

@api_view(["PUT"])
@permission_classes([IsAuth])
@authentication_classes([AuthBySessionID])
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

@swagger_auto_schema(
    method="put",
    manual_parameters=[
        openapi.Parameter(
            name="transfer_id",
            in_=openapi.IN_PATH,
            type=openapi.TYPE_INTEGER,
            description="ID заявки, формируемой создателем",
        ),
    ],
    responses={
        status.HTTP_200_OK: TransferSerializer(),
        status.HTTP_400_BAD_REQUEST: "Не заполнены обязательные поля: [поля, которые не заполнены]",
        status.HTTP_403_FORBIDDEN: "Доступ запрещен",
        status.HTTP_404_NOT_FOUND: "Заявка не найдена",
        status.HTTP_405_METHOD_NOT_ALLOWED: "Заявка не в статусе 'Черновик'",
    },
)

@api_view(["PUT"])
@permission_classes([IsAuth])
@authentication_classes([AuthBySessionID])
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

@swagger_auto_schema(
    method="put",
    manual_parameters=[
        openapi.Parameter(
            name="transfer_id",
            in_=openapi.IN_PATH,
            type=openapi.TYPE_INTEGER,
            description="ID заявки, обрабатываемой модератором",
        ),
    ],
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            "status": openapi.Schema(
                type=openapi.TYPE_STRING,
                description="Новый статус заявки ('completed' для завершения, 'rejected' для отклонения)",
            ),
        },
        required=["status"],
    ),
    responses={
        status.HTTP_200_OK: TransferSerializer(),
        status.HTTP_403_FORBIDDEN: "Вы не вошли в систему как модератор",
        status.HTTP_404_NOT_FOUND: "Заявка не найдена",
        status.HTTP_405_METHOD_NOT_ALLOWED: "Заявка не в статусе 'Сформирован'",
    },
)

@api_view(["PUT"])
@permission_classes([IsManagerAuth])
@authentication_classes([AuthBySessionID])
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
    transfer.moderator = request.user
    transfer.heaviest_baggage = transfer.baggages.aggregate(max_weight=Max('weight'))['max_weight']
    transfer.completion_date = timezone.now().date()
    transfer.save()

    serializer = TransferSerializer(transfer, many=False)

    return Response(serializer.data)

@swagger_auto_schema(
    method="delete",
    manual_parameters=[
        openapi.Parameter(
            name="transfer_id",
            in_=openapi.IN_PATH,
            type=openapi.TYPE_INTEGER,
            description="ID удаляемой заявки",
        ),
    ],
    responses={
        status.HTTP_200_OK: TransferSerializer(),
        status.HTTP_403_FORBIDDEN: "Доступ запрещен",
        status.HTTP_404_NOT_FOUND: "Заявка не найдена",
        status.HTTP_405_METHOD_NOT_ALLOWED: "Удаление возможно только для заявки в статусе 'Черновик'",
    },
)

@api_view(["DELETE"])
@permission_classes([IsAuth])
@authentication_classes([AuthBySessionID])
def delete_transfer(request, transfer_id):
    try:
        transfer = Transfer.objects.get(pk=transfer_id)
    except Transfer.DoesNotExist:
        return Response({"error": "Заявка не найдена"}, status=status.HTTP_404_NOT_FOUND)

    if not request.user.is_superuser and transfer.user != request.user:
        return Response(status=status.HTTP_403_FORBIDDEN)

    if transfer.status != 'draft':
        return Response({'error': 'Нельзя удалить данную заявку'}, status=status.HTTP_405_METHOD_NOT_ALLOWED)

    transfer.status = 'deleted'
    transfer.save()
    serializer = TransferSerializer(transfer, many=False)

    return Response(serializer.data)

@swagger_auto_schema(
    method="delete",
    manual_parameters=[
        openapi.Parameter(
            name="baggage_id",
            in_=openapi.IN_PATH,
            type=openapi.TYPE_INTEGER,
            description="ID багажа в заявке"
        ),
        openapi.Parameter(
            name="transfer_id",
            in_=openapi.IN_PATH,
            type=openapi.TYPE_INTEGER,
            description="ID заявки"
        ),
    ],
    responses={
        status.HTTP_200_OK: TransferSerializer(),
        status.HTTP_403_FORBIDDEN: "Доступ запрещен",
        status.HTTP_404_NOT_FOUND: "Связь между багажом и заявкой не найдена",
    },
)

@api_view(["DELETE"])
@permission_classes([IsAuth])
@authentication_classes([AuthBySessionID])
def delete_baggage_from_transfer(request, baggage_id, transfer_id):
    try:
        baggage_transfer = BaggageTransfer.objects.get(baggage_id=baggage_id, transfer_id=transfer_id)
    except BaggageTransfer.DoesNotExist:
        return Response({"error": "Связь между багажом и заявкой не найдена"}, status=status.HTTP_404_NOT_FOUND)

    if not request.user.is_superuser and baggage_transfer.transfer.user != request.user:
        return Response(status=status.HTTP_403_FORBIDDEN)

    baggage_transfer.delete()

    try:
        transfer = Transfer.objects.get(pk=transfer_id)
    except Transfer.DoesNotExist:
        return Response({"error": "Заявка не найдена после удаления багажа"}, status=status.HTTP_404_NOT_FOUND)

    serializer = TransferSerializer(transfer, many=False)

    return Response(serializer.data, status=status.HTTP_200_OK)

@swagger_auto_schema(
    method="put",
    manual_parameters=[
        openapi.Parameter(
            name="baggage_id",
            in_=openapi.IN_PATH,
            type=openapi.TYPE_INTEGER,
            description="ID багажа в заявке"
        ),
        openapi.Parameter(
            name="transfer_id",
            in_=openapi.IN_PATH,
            type=openapi.TYPE_INTEGER,
            description="ID заявки"
        ),
    ],
    responses={
        status.HTTP_200_OK: BaggageTransferSerializer(),
        status.HTTP_403_FORBIDDEN: "Доступ запрещен",
        status.HTTP_404_NOT_FOUND: "Заявка не найден",
    },
)

@api_view(["PUT"])
@permission_classes([IsAuth])
@authentication_classes([AuthBySessionID])
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

@swagger_auto_schema(
    method="post",
    request_body=UserSerializer,
    responses={
        status.HTTP_201_CREATED: "Created",
        status.HTTP_400_BAD_REQUEST: "Bad Request",
    },
)

@api_view(["POST"])
@permission_classes([AllowAny])
def register(request):
    serializer = UserSerializer(data=request.data)

    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@swagger_auto_schema(
    method="put",
    request_body=UserSerializer,
    responses={
        status.HTTP_200_OK: UserSerializer(),
        status.HTTP_400_BAD_REQUEST: "Bad Request",
        status.HTTP_403_FORBIDDEN: "Forbidden",
    },
)

@api_view(["PUT"])
@permission_classes([IsAuth])
@authentication_classes([AuthBySessionID])
def update_user(request, user_id):
    serializer = UserSerializer(request.user, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@swagger_auto_schema(
    method="post",
    manual_parameters=[
        openapi.Parameter(
            "username",
            type=openapi.TYPE_STRING,
            description="username",
            in_=openapi.IN_FORM,
            required=True,
        ),
        openapi.Parameter(
            "password",
            type=openapi.TYPE_STRING,
            description="password",
            in_=openapi.IN_FORM,
            required=True,
        ),
    ],
    responses={
        status.HTTP_200_OK: "OK",
        status.HTTP_400_BAD_REQUEST: "Bad Request",
    },
)

@api_view(["POST"])
@parser_classes((MultiPartParser, FormParser))
@permission_classes([AllowAny])
def login(request):
    username = request.data.get("username")
    password = request.data.get("password")
    user = authenticate(username=username, password=password)
    if user is not None:
        session_id = str(uuid.uuid4())
        session_storage.set(session_id, username)
        response = Response(status=status.HTTP_200_OK)
        response.set_cookie("session_id", session_id, samesite="Lax")
        return response
    return Response(
        {"error": "Invalid Credentials"}, status=status.HTTP_400_BAD_REQUEST
    )

@swagger_auto_schema(
    method="post",
    responses={
        status.HTTP_204_NO_CONTENT: "No content",
        status.HTTP_403_FORBIDDEN: "Forbidden",
    },
)


@api_view(["POST"])
def logout(request):
    session_id = request.COOKIES["session_id"]
    if session_storage.exists(session_id):
        session_storage.delete(session_id)
        return Response(status=status.HTTP_204_NO_CONTENT)
    return Response(status=status.HTTP_403_FORBIDDEN)
