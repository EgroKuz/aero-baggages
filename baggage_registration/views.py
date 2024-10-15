from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse
from django.contrib.auth.models import User
from .models import Transfer, Baggage, BaggageTransfer
from django.db import connection
from django.utils import timezone
from django.contrib.auth.decorators import login_required


def baggages(request):
    weight = request.GET.get('weight', '')
    if weight:
        baggages = Baggage.objects.filter(weight__icontains=weight)
    else:
        baggages = Baggage.objects.all()

    draft_transfer = Transfer.objects.filter(status='draft').first()
    for baggage in baggages:
        baggage.added = baggage.id in BaggageTransfer.objects.filter(transfer=draft_transfer).values_list('baggage_id', flat=True)

    return render(request, 'index.html', {
        'baggages': baggages,
        'weight': weight,
        'draft_transfer': draft_transfer,
        'baggages_to_migrant': len(draft_transfer.baggages.all()) if draft_transfer else None
    })

def baggage(request, baggage_id):
    needed_baggage = Baggage.objects.get(id=baggage_id)
    return render(request, 'baggage.html', {'baggage': needed_baggage})


def transfer(request, transfer_id):
    transfer = get_object_or_404(Transfer, pk=transfer_id)
    if transfer.status == 'deleted':
        return render(request, 'transfer.html', {'error': 'Невозможно посмотреть данную заявку'})
    if not transfer:
        return redirect('baggages')

    baggage_transfer = BaggageTransfer.objects.filter(transfer=transfer)
    baggages = [
        {
            'baggage': bt.baggage,
            'fragility': 'Хрупкий' if bt.fragility else 'Не хрупкий'
        }
        for bt in baggage_transfer
    ]

    return render(request, 'transfer.html', {'baggages': baggages, 'transfer': transfer, 'num_of_baggages': len(baggages)})

def remove_transfer(request, transfer_id):
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE baggage_registration_transfer SET status = 'deleted' WHERE id = %s",
            [transfer_id]
        )
    return redirect('baggages')

def add_baggage_to_transfer(request, baggage_id):
    baggage = get_object_or_404(Baggage, pk=baggage_id)
    draft_transfer = Transfer.objects.filter(status='draft', user=request.user).first()
    if draft_transfer is None:
        draft_transfer = Transfer.objects.create(
            transfer_date=timezone.now().date(),
            user=request.user,
            owner_name='Кузнецов В.В.',
            flight='CH9447'
        )
        draft_transfer.save()
    if BaggageTransfer.objects.filter(transfer=draft_transfer, baggage=baggage).exists():
        weight = request.POST.get('weight', '')
        if weight:
            return redirect(f"/?weight={weight}")
        else:
            return redirect('baggages')

    baggage_transfer = BaggageTransfer(
        transfer=draft_transfer,
        baggage=baggage,
        fragility=False
    )
    baggage_transfer.save()

    weight = request.POST.get('weight', '')
    if weight:
        return redirect(f"/?weight={weight}")
    else:
        return redirect('baggages')
