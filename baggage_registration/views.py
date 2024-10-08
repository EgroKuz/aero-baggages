from django.shortcuts import render
from django.http import HttpResponse
from baggages_data import BAGGAGES_DATA
from transfers_data import DRAFT_TRANSFER
from django.db import connection

def baggages(request):
    weight = request.GET.get('weight', '')
    baggages = search_baggage(weight)
    baggages_to_migrant = sum(1 for baggage in DRAFT_TRANSFER['baggages'])
    return render(request, 'index.html',{
        'baggages': baggages,
        'weight': weight,
        'draft_transfer': DRAFT_TRANSFER,
        'baggages_to_migrant': baggages_to_migrant
    })
def baggage(request, baggage_id):
    baggage = get_baggage_by_id(baggage_id)
    if not baggage:
        return render(request, '404.html', status=404)
    return render(request, 'baggage.html', {'baggage': baggage})

def transfer(request, transfer_id):
    transfer = get_transfer_by_id(transfer_id)
    baggages = []
    for baggage_id in transfer['baggages']:
        baggage = get_baggage_by_id(baggage_id)
        if baggage:
            baggages.append(baggage)
    return render(request, 'transfer.html', {'baggages': baggages, 'transfer': transfer})

def search_baggage(weight):
    result = []
    for baggage in BAGGAGES_DATA:
        if weight in baggage["weight"]:
            result.append(baggage)
    return result

def get_baggage_by_id(baggage_id):
    for baggage in BAGGAGES_DATA:
        if baggage_id == baggage['id']:
            return baggage
    return None

def get_transfer_by_id(transfer_id):
    return DRAFT_TRANSFER