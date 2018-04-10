import json
from shapely.geometry import shape
from shapely import geometry
from shapely.ops import cascaded_union
from rasterio import features
import requests
import os
from skimage import filters, morphology, measure, color, segmentation
from scipy import ndimage as ndi


# CONSTANTS
osm_buildings_sanjuan = 'https://s3.amazonaws.com/gbdx-training/blue_roofs/hotosm_pri_building_polygons_san_juan.geojson'


# FUNCTIONS
def from_geojson(source):
    if source.startswith('http'):
        response = requests.get(source)
        geojson = json.loads(response.content)
    else:
        if os.path.exists(source):
            with open(source, 'r') as f:
                geojson = json.loads(f.read())
        else:
            raise ValueError("File does not exist: {}".format(source))

    geometries = []
    feats = []
    for f in geojson['features']:
        geom = geometry.shape(f['geometry'])
        feats.append({'geometry': geom, 'properties': {}})
        geometries.append(geom)

    return geometries, feats


def to_geojson(l):
    g = {'crs'     : {u'properties': {u'name': u'urn:ogc:def:crs:OGC:1.3:CRS84'}, 'type': 'name'},
         'features': [{'geometry': d['geometry'].__geo_interface__, 'properties': d['properties'], 'type': 'Feature'}
                      for d in l],
         'type'    : u'FeatureCollection'}

    gj = json.dumps(g)

    return gj


def labels_to_polygons(labels_array, image_affine, ignore_label=0):
    # create polygon generator object
    polygon_generator = features.shapes(labels_array.astype('uint8'),
                                        mask=labels_array <> ignore_label,
                                        transform=image_affine)
    # Extract out the individual polygons, fixing any invald geometries using buffer(0)
    polygons = [{'geometry': shape(g).buffer(0), 'properties': {'id': v}} for g, v in polygon_generator]

    return polygons


def find_blue_polys(image, lower_blue_hue=.60, upper_blue_hue=.67, segment_blobs=True, blm=True,
                    min_size=120, blobs_erosion=10, binary_opening_radius=2):

    if blm is True:
        rgb = image.base_layer_match(blm=True, access_token=os.environ.get('MAPBOX_API_KEY'))
    else:
        rgb = image.rgb()
    hsv = color.rgb2hsv(rgb)
    mask = (hsv[:, :, 0] <= upper_blue_hue) & (hsv[:, :, 0] >= lower_blue_hue)
    selem = morphology.disk(radius=binary_opening_radius)
    mask_cleaned = morphology.binary_opening(mask, selem=selem)
    mask_cleaned = morphology.remove_small_objects(mask_cleaned, min_size=min_size, connectivity=1)
    mask_cleaned = morphology.remove_small_holes(mask_cleaned, min_size=min_size, connectivity=1)
    if segment_blobs is True:
        selem = morphology.disk(radius=blobs_erosion)
        cores = morphology.label(morphology.erosion(mask_cleaned, selem=selem))
        edges = morphology.label(mask_cleaned)
        edge_distance = ndi.distance_transform_edt(edges)
        mask_labels = morphology.label(
            segmentation.watershed(-edge_distance, markers=cores, mask=mask_cleaned) + mask_cleaned)
    else:
        mask_labels = measure.label(mask_cleaned, background=0)
    blue_polys = labels_to_polygons(mask_labels, image.affine, ignore_label=0)

    return blue_polys


def filter_blue_polys(blue_polygons, bldgs):
    buildings_merge = cascaded_union([f['geometry'] for f in bldgs])
    filtered_polys = [poly for poly in blue_polygons if poly['geometry'].intersects(buildings_merge)]

    return filtered_polys





