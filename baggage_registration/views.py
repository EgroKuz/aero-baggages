from rest_framework.response import Response
from rest_framework import status
from .serializers import *
from django.db.models import Max
from .minio import *
from django.contrib.auth import authenticate
from .models import *
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from django.db.models import Max
from django.contrib.auth import authenticate, login, logout
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
    method='get',
    manual_parameters=[
        openapi.Parameter(
            name="baggage_weight",
            in_=openapi.IN_QUERY,
            description="Фильтрация по совпадению веса багажа",
            type=openapi.TYPE_STRING,
        ),
    ],
    responses={
        status.HTTP_200_OK: openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "baggages": openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Items(type=openapi.TYPE_OBJECT),
                    description="Список багажей"
                ),
                "draft_transfer": openapi.Schema(
                    type=openapi.TYPE_NUMBER,
                    description="ID черновика заявки, если существует",
                    nullable=True
                ),
                "baggages_to_transfer": openapi.Schema(
                    type=openapi.TYPE_NUMBER,
                    description="Количество багажей в черновике",
                    nullable=True
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
            draft_transfer = Transfer.objects.filter(status='draft').first()
            baggages_to_transfer = len(draft_transfer.baggages.all()) if draft_transfer else None
        except Transfer.DoesNotExist:
            draft_transfer = None

    response = {
        'baggages': serializer.data,
        'draft_transfer': draft_transfer.pk if draft_transfer else None,
        'baggages_to_transfer': baggages_to_transfer
    }
    return Response(response, status=status.HTTP_200_OK)

@swagger_auto_schema(
    method="get",
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
    responses={
        status.HTTP_200_OK: BaggageSerializer(),
        status.HTTP_403_FORBIDDEN: "Вы не вошли в систему как модератор",
        status.HTTP_404_NOT_FOUND: "Багаж не найден",
        status.HTTP_400_BAD_REQUEST: "Неверные данные",
    },
)

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

    return Response(BaggageSerializer(updated_baggage).data, status=status.HTTP_200_OK)

@swagger_auto_schema(
    method="delete",
    responses={
        status.HTTP_200_OK: BaggageSerializer(many=True),
        status.HTTP_403_FORBIDDEN: "Вы не вошли в систему как модератор",
        status.HTTP_404_NOT_FOUND: "Багаж не найден",
    },
)

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

@swagger_auto_schema(
    method="post",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            "image": openapi.Schema(type=openapi.TYPE_FILE, description="Новое изображение для багажа"),
        },
        required=["image"]
    ),
    responses={
        status.HTTP_200_OK: BaggageSerializer(),
        status.HTTP_400_BAD_REQUEST: "Изображение не предоставлено",
        status.HTTP_403_FORBIDDEN: "Вы не вошли в систему как модератор",
        status.HTTP_404_NOT_FOUND: "Багаж не найден"
    },
)

@api_view(["POST"])
def update_baggage_image(request, baggage_id):
    try:
        baggage = Baggage.objects.get(pk=baggage_id)
    except Baggage.DoesNotExist:
        return Response({"Ошибка": "Багаж не найден"}, status=status.HTTP_404_NOT_FOUND)

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

    if not request.user or not request.user.is_authenticated:
        return Response({'error': 'Пользователь не аутентифицирован'}, status=status.HTTP_401_UNAUTHORIZED)

    try:
        baggage = Baggage.objects.get(pk=baggage_id)
    except Baggage.DoesNotExist:
        return Response({'error': 'Багаж не найден'}, status=status.HTTP_404_NOT_FOUND)

    draft_transfer = Transfer.objects.filter(status='draft').first()

    if draft_transfer is None:
        draft_transfer = Transfer.objects.create(
            creation_date=timezone.now().date(),
            user=request.user
        )


    if BaggageTransfer.objects.filter(transfer=draft_transfer, baggage=baggage).exists():
        return Response({'error': 'Багаж уже добавлен в перемещение'}, status=status.HTTP_405_METHOD_NOT_ALLOWED)

    try:
        BaggageTransfer.objects.create(
            transfer=draft_transfer,
            baggage=baggage,
            fragility=False,
        )
    except Exception as e:
        return Response({'error': f'Ошибка при создании связи: {str(e)}'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    serializer = TransferSerializer(draft_transfer)
    return Response(serializer.data, status=status.HTTP_201_CREATED)

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
    responses={
        status.HTTP_200_OK: openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "id": openapi.Schema(
                    type=openapi.TYPE_INTEGER,
                    title="ID",
                    readOnly=True,
                ),
                "baggages_to_transfer": openapi.Schema(
                    type=openapi.TYPE_INTEGER,
                    title="Baggages to transfer",
                    readOnly=True,
                ),
                "user": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    title="Owner",
                    readOnly=True,
                ),
                "baggages": openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    title="Baggages",
                    items=openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            "id": openapi.Schema(type=openapi.TYPE_INTEGER),
                            "weight": openapi.Schema(type=openapi.TYPE_INTEGER),
                            "number": openapi.Schema(type=openapi.TYPE_STRING),
                            "description": openapi.Schema(type=openapi.TYPE_STRING),
                            "image": openapi.Schema(type=openapi.TYPE_STRING, format="uri"),
                        },
                    ),
                    readOnly=True,
                ),
                "transfer_date": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    format="date",
                    title="Запланированная дата отправки",
                    nullable=True,
                ),
                "flight": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    title="Номер рейса",
                    maxLength=50,
                    nullable=True,
                ),
                "owner_name": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    title="Имя владельца",
                    maxLength=50,
                    nullable=True,
                ),
                "moderator": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    title="Moderator",
                    readOnly=True,
                    nullable=True,
                ),
                "status": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    title="Статус",
                    enum=["draft", 'deleted', 'formed', 'completed', 'rejected'],
                ),
                "creation_date": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    format="date-time",
                    title="Дата создания",
                ),
                "formation_date": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    format="date-time",
                    title="Дата формирования",
                    nullable=True,
                ),
                "completion_date": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    format="date-time",
                    title="Дата завершения",
                    nullable=True,
                ),
                "heaviest_baggage": openapi.Schema(
                    type=openapi.TYPE_INTEGER,
                    title="Самый тяжелый багаж",
                    nullable=True,
                ),
            },
        ),
        status.HTTP_403_FORBIDDEN: "Вы не вошли в систему",
        status.HTTP_404_NOT_FOUND: "Переход не найден",
    }
)

@api_view(["GET"])
@permission_classes([IsAuth])
@authentication_classes([AuthBySessionID])
def get_transfer_by_id(request, transfer_id):

    try:
        transfer = Transfer.objects.get(pk=transfer_id)
        print(f"Owner of transfer {transfer_id}: {transfer.user} (type: {type(transfer.user)})")  # Кто владелец?
        print(f"Current User ID: {request.user.id}")
        print(f"Owner ID from Transfer: {transfer_id}")
    except Transfer.DoesNotExist:
        return Response({"error": "Заявка не найдена"}, status=status.HTTP_404_NOT_FOUND)

    print(f"Current User: {request.user} (type: {type(request.user)})")  # Кто запрашивает?

    if not request.user.is_superuser and transfer.user != request.user:
        return Response({"error": "У вас нет доступа"}, status=status.HTTP_403_FORBIDDEN)

    serializer = SingleTransferSerializer(transfer, many=False)
    return Response(serializer.data)


@swagger_auto_schema(
    method="put",
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
    responses={
        status.HTTP_200_OK: TransferSerializer(),
        status.HTTP_403_FORBIDDEN: "Доступ запрещен",
        status.HTTP_404_NOT_FOUND: "Связь между багажом и заявкой не найдена",
    },
)

@api_view(["DELETE"])
@permission_classes([IsAuth])
@authentication_classes([AuthBySessionID])
def delete_baggage_from_transfer(request, transfer_id, baggage_id):
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
def update_user(request):
    cleaned_data = {key: value for key, value in request.data.items() if value != ""}
    print("Received cleaned request data:", cleaned_data)

    serializer = UserSerializer(request.user, data=cleaned_data, partial=True)
    if serializer.is_valid():
        print("Validated successfully")
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
        status.HTTP_200_OK: openapi.Response(
            description="User successfully logged in",
            schema=UserSerializer()
        ),
        status.HTTP_400_BAD_REQUEST: openapi.Response(
            description="Invalid credentials",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "error": openapi.Schema(type=openapi.TYPE_STRING)
                }
            )
        ),
    },
)

@api_view(["POST"])
@parser_classes((FormParser, ))
@permission_classes([AllowAny])
def login(request):
    username = request.data.get("username")
    password = request.data.get("password")
    user = authenticate(username=username, password=password)
    if user is not None:
        session_id = str(uuid.uuid4())
        session_storage.set(session_id, username)
        serializer = UserSerializer(user)
        response = Response(serializer.data, status=status.HTTP_200_OK)
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
    session_id = request.COOKIES.get("session_id")  # 👈 Безопасный доступ

    if not session_id:
        return Response({"error": "Session not found"}, status=status.HTTP_403_FORBIDDEN)

    print(f"🛑 Удаление session_id: {session_id}")

    if session_storage.exists(session_id):
        session_storage.delete(session_id)
        response = Response(status=status.HTTP_204_NO_CONTENT)
        response.delete_cookie("session_id")
        return response

    return Response({"error": "Invalid session"}, status=status.HTTP_403_FORBIDDEN)

@swagger_auto_schema(
    method="post",
    responses={
        status.HTTP_200_OK: "Роль менеджера успешно выдана",
        status.HTTP_403_FORBIDDEN: "Доступ запрещён",
        status.HTTP_404_NOT_FOUND: "Пользователь не найден",
    },
)
@api_view(["POST"])
@permission_classes([IsManagerAuth])
@authentication_classes([AuthBySessionID])
def assign_manager_role(request, user_id):
    try:
        user = User.objects.get(pk=user_id)
        user.is_staff = True
        user.save()
        return Response(
            {"message": f"Пользователю {user.username} выданы права менеджера."},
            status=status.HTTP_200_OK,
        )
    except User.DoesNotExist:
        return Response({"error": "Пользователь не найден."}, status=status.HTTP_404_NOT_FOUND)


@swagger_auto_schema(
    method="get",
    responses={
        status.HTTP_200_OK: openapi.Schema(
            type=openapi.TYPE_ARRAY,
            items=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "id": openapi.Schema(type=openapi.TYPE_INTEGER, description="ID пользователя"),
                    "username": openapi.Schema(type=openapi.TYPE_STRING, description="Имя пользователя"),
                    "email": openapi.Schema(type=openapi.TYPE_STRING, description="Электронная почта пользователя"),
                    "is_staff": openapi.Schema(type=openapi.TYPE_BOOLEAN, description="Является ли сотрудником"),
                    "is_superuser": openapi.Schema(type=openapi.TYPE_BOOLEAN, description="Является ли суперпользователем"),
                },
            ),
        ),
        status.HTTP_403_FORBIDDEN: "Доступ запрещён",
    },
)
@api_view(['GET'])
@permission_classes([IsManagerAuth])
def get_user_list(request):

    users = User.objects.all()
    serializer = UserListSerializer(users, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)