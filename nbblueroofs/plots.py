from builtins import str
import jinja2
import json
import folium
from shapely.geometry import box
from gbdxtools import CatalogImage
from gbdxtools import IdahoImage
import numpy as np
from matplotlib import pyplot as plt, colors
import plotly.graph_objs as go
from branca.element import Element, Figure
from plotly.offline.offline import _plot_html
from plotly.graph_objs import Line

# CONSTANTS
TMS_1040010039BAAF00 = 'https://s3.amazonaws.com/notebooks-small-tms/1040010039BAAF00/{z}/{x}/{y}.png'

COLORS = {'gray'       : '#8F8E8E',
          'white'      : '#FFFFFF',
          'brightgreen': '#00FF17',
          'red'        : '#FF0000',
          'cyan'       : '#1FFCFF'}


def bldg_styler(x):
    return {'fillOpacity': .25,
            'color'      : COLORS['cyan'] if x['properties']['blue'] == True else COLORS['white'],
            'fillColor'  : COLORS['gray'],
            'weight'     : 1}

# FUNCTIONS
def folium_map(geojson_to_overlay, layer_name, location, style_function=None, tiles='Stamen Terrain', zoom_start=16,
               show_layer_control=True, width='100%', height='75%', attr=None, map_zoom=18, max_zoom=20, tms=False,
               zoom_beyond_max=None, base_tiles='OpenStreetMap', opacity=1):
    m = folium.Map(location=location, zoom_start=zoom_start, width=width, height=height, max_zoom=map_zoom,
                   tiles=base_tiles)
    tiles = folium.TileLayer(tiles=tiles, attr=attr, name=attr, max_zoom=max_zoom)
    if tms is True:
        options = json.loads(tiles.options)
        options.update({'tms': True})
        tiles.options = json.dumps(options, sort_keys=True, indent=2)
        tiles._template = jinja2.Template(u"""
        {% macro script(this, kwargs) %}
            var {{this.get_name()}} = L.tileLayer(
                '{{this.tiles}}',
                {{ this.options }}
                ).addTo({{this._parent.get_name()}});
        {% endmacro %}
        """)
    if zoom_beyond_max is not None:
        options = json.loads(tiles.options)
        options.update({'maxNativeZoom': zoom_beyond_max, 'maxZoom': max_zoom})
        tiles.options = json.dumps(options, sort_keys=True, indent=2)
        tiles._template = jinja2.Template(u"""
        {% macro script(this, kwargs) %}
            var {{this.get_name()}} = L.tileLayer(
                '{{this.tiles}}',
                {{ this.options }}
                ).addTo({{this._parent.get_name()}});
        {% endmacro %}
        """)
    if opacity < 1:
        options = json.loads(tiles.options)
        options.update({'opacity': opacity})
        tiles.options = json.dumps(options, sort_keys=True, indent=2)
        tiles._template = jinja2.Template(u"""
        {% macro script(this, kwargs) %}
            var {{this.get_name()}} = L.tileLayer(
                '{{this.tiles}}',
                {{ this.options }}
                ).addTo({{this._parent.get_name()}});
        {% endmacro %}
        """)

    tiles.add_to(m)
    if style_function is not None:
        gj = folium.GeoJson(geojson_to_overlay, overlay=True, name=layer_name, style_function=style_function)
    else:
        gj = folium.GeoJson(geojson_to_overlay, overlay=True, name=layer_name)
    gj.add_to(m)

    if show_layer_control is True:
        folium.LayerControl().add_to(m)

    return m


def get_idaho_tms_ids(image):
    ms_parts = {str(p['properties']['attributes']['idahoImageId']): str(
            p['properties']['attributes']['vendorDatasetIdentifier'].split(':')[1])
        for p in image._find_parts(image.cat_id, 'MS')}

    pan_parts = {str(p['properties']['attributes']['vendorDatasetIdentifier'].split(':')[1]): str(
            p['properties']['attributes']['idahoImageId'])
        for p in image._find_parts(image.cat_id, 'pan')}

    ms_idaho_ids = [(k, box(*IdahoImage(k).bounds).intersection(box(*image.bounds)).area) for k in list(ms_parts.keys()) if
                    box(*IdahoImage(k).bounds).intersects(box(*image.bounds))]
    min_area = 0
    for ms_idaho_id in ms_idaho_ids:
        if ms_idaho_id[1] >= min_area:
            min_area = ms_idaho_id[1]
            the_ms_idaho_id = ms_idaho_id[0]

    pan_idaho_id = pan_parts[ms_parts[the_ms_idaho_id]]

    idaho_ids = {'ms_id' : the_ms_idaho_id,
                 'pan_id': pan_idaho_id}
    return idaho_ids


def get_idaho_tms_url(source_catid_or_image, gbdx):
    if type(source_catid_or_image) == str:
        image = CatalogImage(source_catid_or_image)
    elif '_ipe_op' in list(source_catid_or_image.__dict__.keys()):
        image = source_catid_or_image
    else:
        err = "Invalid type for source_catid_or_image. Must be either a Catalog ID (string) or CatalogImage object"
        raise TypeError(err)

    url_params = get_idaho_tms_ids(image)
    url_params['token'] = str(gbdx.gbdx_connection.access_token)
    url_params['z'] = '{z}'
    url_params['x'] = '{x}'
    url_params['y'] = '{y}'
    url_params['bucket'] = str(image.ipe.metadata['image']['tileBucketName'])
    url_template = 'https://idaho.geobigdata.io/v1/tile/{bucket}/{ms_id}/{z}/{x}/{y}?bands=4,2,1&token={token}&panId={pan_id}'
    url = url_template.format(**url_params)

    return url


def plot_array(array, subplot_ijk, title="", font_size=18, cmap=None):
    sp = plt.subplot(*subplot_ijk)
    sp.set_title(title, fontsize=font_size)
    plt.axis('off')
    plt.imshow(array, cmap=cmap)


def plot_plotly(chart, width='100%', height=525):
    # produce the html in Ipython compatible format
    plot_html, plotdivid, width, height = _plot_html(chart, {'showLink': False}, True, width, height, True)
    # define the plotly js library source url
    head = '<script src="https://cdn.plot.ly/plotly-latest.min.js"></script>'
    # extract the div element from the ipython html
    div = plot_html[0:plot_html.index('<script')]
    # extract the script element from the ipython html
    script = plot_html[plot_html.index('Plotly.newPlot'):plot_html.index('});</script>')] + ';'
    # combine div and script to build the body contents
    body = '<body>{div}<script>{script}</script></body>'.format(div=div, script=script)
    # instantiate a figure object
    figure = Figure()
    # add the head
    figure.header.add_child(Element(head))
    # add the body
    figure.html.add_child(Element(body))

    return figure


def plot_ribbon(df, x, ylower, yupper, name, ylab, ymax_factor=1, fillcolor='rgba(21,40,166,0.2)'):
    # Create a trace
    trace1 = go.Scatter(x=df[x],
                        y=df[yupper],
                        fill='tonexty',
                        fillcolor=fillcolor,
                        line=Line(color='transparent'),
                        showlegend=False,
                        name=name)

    trace2 = go.Scatter(x=df[x],
                        y=df[ylower],
                        fill='tonexty',
                        fillcolor='transparent',
                        line=Line(color='transparent'),
                        showlegend=False,
                        name=name)

    graph_data = [trace2, trace1]
    yaxis = dict(title=ylab,
                 range=(0, max(df[yupper]) * ymax_factor))
    graph_layout = go.Layout(yaxis=yaxis, showlegend=False)
    fig = go.Figure(data=graph_data, layout=graph_layout)

    return fig


def plot_results(df, x, y, name, ylab, ymax_factor=1):
    # Create a trace
    trace = go.Scatter(x=df[x],
                       y=df[y],
                       name=name)
    graph_data = [trace]
    yaxis = dict(title=ylab,
                 range=(0, max(df[y])*ymax_factor))
    graph_layout = go.Layout(yaxis=yaxis, showlegend=False)
    fig = go.Figure(data=graph_data, layout=graph_layout)

    return fig


def plot_multi_trace(df, x, y, factor_var, ymax_factor=1.):
    graph_layout = go.Layout(showlegend=True)

    graph_data = []
    factor_vals = df[factor_var].unique()
    domain_breaks = np.linspace(0, 1, len(factor_vals) + 1)
    for i, factor_val in enumerate(factor_vals):
        df_subset = df[df[factor_var] == factor_val]
        # Create a trace
        x_anchor = 'x1'
        y_anchor = 'y{}'.format(i + 1)
        new_trace = go.Scatter(x=df_subset[x],
                               y=df_subset[y],
                               name=factor_val,
                               mode='lines+markers',
                               xaxis=x_anchor,
                               yaxis=y_anchor)
        graph_data.append(new_trace)
        yaxis = dict(range=(0, max(df_subset[y]) * ymax_factor),
                     anchor=x_anchor,
                     domain=(domain_breaks[i], domain_breaks[i + 1] - 0.03))
        if i == 0:
            y_axis_name = 'yaxis'
        else:
            y_axis_name = 'yaxis{}'.format(i + 1)
        graph_layout[y_axis_name] = yaxis.copy()
    fig = go.Figure(data=graph_data, layout=graph_layout)

    return fig
