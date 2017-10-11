import json
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from django.shortcuts import render

# Create your views here.
from django.http import HttpResponse
from django.utils.datastructures import MultiValueDictKeyError


"""
    request
"""
def index(request):
    
    return HttpResponse("Please use the API call \"search\"<br>e.g., http://localhost:8000/eventDetection/search?extent=POINT(1%2010)&reference_date=2016-01-01&event_date=2017-01-01&keys=Camp")


"""
    Accepting request, create and send query to strabonish-endpoint.
    Getting and parsing the response
"""
def search(request):
    # Get the parameters from user
    try:
        extent          = request.GET.get("extent", None)
        keys            = request.GET.get('keys', None)
        event_date      = request.GET.get('event_date', None)
        reference_date  = request.GET.get('reference_date', None)
    except MultiValueDictKeyError as e:
        return HttpResponseBadRequest('Missing parameters. Please provide all: <ol><li>extent</li><li>event_date</li><li>reference_date</li><li>keys</li></ol>')

    # try parsing dates according to ISO8601
    try:
        if event_date and event_date != 'null':
            event_date = datetime.strptime(event_date,"%Y-%m-%d")
            
        if reference_date and reference_date != 'null':
            reference_date = datetime.strptime(reference_date,"%Y-%m-%d")
     
    except ValueError as e:
        return HttpResponseBadRequest('date should be <b>ISO8601</b> format')
    
    if keys:
        keys = keys.replace(",", "|");
    
    # Build query, make request, get response.
    query = q_builder(extent, keys, event_date, reference_date)
    print("Event-Retrieve query:\t" + str(query))
    
    hrs     = {'content-type': 'application/x-www-form-urlencoded', 'Accept': 'application/sparql-results+xml'}
    url     = "http://strabon:8080/strabon/Query"
    pars    = {"query": query, "format": 'SPARQL/XML'}
    response= requests.post(url, params = pars, headers = hrs)
    print("status-code: " + str(response.status_code) + "\treason: " + str(response.reason))
    
    # Verbose print. Un-comment it only if you need to see the response.
    """
    print("Response's text:\n" + str(response.text))
    print("\n...end of response's text.\n\n")
    """
    
    # parse xml data to build the objects
    tree    = ET.ElementTree(ET.fromstring(response.text))
    results = tree.find('{http://www.w3.org/2005/sparql-results#}results')
    events  = {}    
    for result in results:
        bindings = result.findall('{http://www.w3.org/2005/sparql-results#}binding')
        
        event_id    = ""
        title       = ""
        date        = ""
        gwkt        = ""
        name        = ""
        # new (pool-party) info:
        thesaurus   = ""
        concepturi  = ""
        link        = ""
        place       = ""
        for binding in bindings:
            
            if binding.attrib['name'] == 'id':
                event_id    = binding[0].text
                                                
            elif binding.attrib['name'] == 't':
                title       = binding[0].text
                
            elif binding.attrib['name'] == 'd':
                date        = binding[0].text
                
            elif binding.attrib['name'] == 'w':
                gwkt        = binding[0].text
                
            elif binding.attrib['name'] == 'n':
                name        = binding[0].text
                
            elif binding.attrib['name'] == 'thesid':
                thesaurus   = binding[0].text
                
            elif binding.attrib['name'] == 'con':
                concepturi  = binding[0].text

            elif binding.attrib['name'] == 'link':
                link        = binding[0].text

            elif binding.attrib['name'] == 'place':
                place        = binding[0].text
        
        area    = {'name': name, 'geometry': gwkt}
        img     = {'link': link, 'place': place}
        entity  = {'thesaurus': thesaurus, 'concept_uri': concepturi}
        event   = {'id': event_id, 'title':title, 'eventDate': date, 'areas':[area], 'entities': [entity], 'images': [img]}
        
        #if event's id already in our dictionary then add all the neccessary info.
        if event_id in events:
            
            if not area in events[event_id]['areas']:
                events[event_id]['areas'].append(area)
                
            if not entity in events[event_id]['entities']:    
                events[event_id]['entities'].append(entity)
                
            if not img in events[event_id]['images']:    
                events[event_id]['images'].append(img)
        else:
            events[event_id] = event
    
    print("\nParsed a total of %d events " % len(events))
    # Uncomment to print all the events with their detailed information.
    """    
    for event_id in events:
        event = events[event_id]
        print("id:", event['id'])
        print("title:", event['title'])
        print("areas:", [ ar['name'] for ar in event['areas']])
        print("entities:", [ en['concept_uri'] for en in event['entities']])
        print("images:", [ im['link'] for im in event['images']])
    """
    
    return HttpResponse(json.dumps(list(events.values())), content_type = "application/json")


"""
    q_builder builds the query according to arguments.
"""
def q_builder(extent, keys, event_date, reference_date):
    
    select ="SELECT distinct ?e ?id ?t ?d ?w ?n ?link ?place ?con ?thesid";
    prefixes = '\n'.join(('PREFIX geo: <http://www.opengis.net/ont/geosparql#>',
                          'PREFIX strdf: <http://strdf.di.uoa.gr/ontology#>',
                          'PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>',
                          'PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>',
                          'PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>',
                          'PREFIX ev: <http://big-data-europe.eu/security/man-made-changes/ontology#>'));
    where = '\n'.join(('WHERE{',
                       ' ?e rdf:type ev:NewsEvent . ',
                       ' ?e ev:hasId ?id . ?e ev:hasTitle ?t . ',
                       ' ?e ev:hasDate ?d . ',
                       ' ?e ev:hasArea ?a . ',
                       ' ?a ev:hasName ?n . ',
                       ' ?a geo:hasGeometry ?g . ',
                       ' ?e ev:hasEntity ?ent . ?ent ev:hasThesaurusId ?thesid . ?ent ev:hasConceptURI ?con . ',
                       ' ?e ev:hasImages ?im . ?im  ev:hasLink ?link . ',
                       ' ?im ev:hasPlace ?place . ',
                       ' ?g geo:asWKT ?w .'));
    filters = []
    
    if event_date and event_date != 'null':
        filters.append("?d < '" + str(event_date) + "'^^xsd:dateTime")
        
    if reference_date and reference_date != 'null':
        filters.append("?d > '" + str(reference_date) + "'^^xsd:dateTime")
        
    if keys and keys != 'null':
        filters.append("regex(?t, '" + str(keys) + "','i')")
        
    if extent and extent != 'null':
        filters.append("strdf:intersects(?w,'" + str(extent) + "')")
        
    if filters and extent != 'null':
        where += 'FILTER('+' && '.join(filters) + ")}"
    else:
        where += '}'

    query = '\n'.join((prefixes, select, where))
    return query
