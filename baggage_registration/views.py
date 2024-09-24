from django.shortcuts import render
from django.http import HttpResponse
from baggages_data import BAGGAGES_DATA
from migrations_data import DRAFT_MIGRATION

def baggages(request):
    number = request.GET.get('number', '')
    baggages = search_baggage(number)
    baggages_to_migrant = sum(1 for baggage in DRAFT_MIGRATION['baggages'])
    return render(request, 'index.html',{
        'baggages': baggages,
        'number': number,
        'draft_migration': DRAFT_MIGRATION,
        'baggages_to_migrant': baggages_to_migrant
    })
def baggage(request, baggage_id):
    baggage = get_baggage_by_id(baggage_id)
    if not baggage:
        return render(request, '404.html', status=404)
    return render(request, 'baggage.html', {'baggage': baggage})

def migration(request, migration_id):
    migration = get_migration_by_id(migration_id)
    baggages = migration['baggages']  # Получаем список багажа
    return render(request, 'migration.html', {'baggages': baggages})

def search_baggage(number):
    result = []
    for baggage in BAGGAGES_DATA:
        if number in baggage["number"]:
            result.append(baggage)
    return result

def get_baggage_by_id(baggage_id):
    for baggage in BAGGAGES_DATA:
        if baggage_id == baggage['id']:
            return baggage
    return None

def get_migration_by_id(migration_id):
    return DRAFT_MIGRATION