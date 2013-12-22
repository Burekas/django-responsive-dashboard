from django.template.loader import render_to_string
from django.template import RequestContext
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core import urlresolvers
from django.utils.importlib import import_module
from django.db.models.fields import FieldDoesNotExist
from django.core.urlresolvers import NoReverseMatch
from django.views.generic.base import TemplateView
import imp
import copy

class Dashboard(object):
    """ Base class for dashboards
    """
    title = ''
    app = ''
    template_name = 'responsive_dashboard/dashboard.html'

    def __init__(self):
        responsive_dashboards['{0}__{1}'.format(self.app, self.title)] = self


class Dashlet(TemplateView):
    """ Base class for dashlets
    Extends TemplateView so it could actually be a view as well.
    """
    title = None
    template_name = 'responsive_dashboard/dashlet.html'
    has_config = False
    template_dict = {}
    require_permissions = ()
    require_permissions_or = () # Allow if any of these permissions are present 
    require_apps = ()
    columns = 1
    responsive = True # Resize to fit mobile devices (depends on css)
    allow_multiple = False # User can add duplicates of this dashlet
    
    def get_context_data(self, **kwargs):
        context = super(Dashlet, self).get_context_data(**kwargs)
        context['title'] = self.title
        context['has_config'] = self.has_config
        return context
    
    def _render(self):
        context = self.get_context_data()
        context['dashlet'] = self
        self.template_dict['dashlet'] = self
        return render_to_string(self.template_name, context, context_instance=RequestContext(self.request))

    def __unicode__(self):
        return self._render()
    
    def set_request(self, request):
        """ Set the html request from the view """
        self.request = request

    def _check_perm(self):
        """ Check if user has permission to view """
        print "checkem!!!!!!!!!!!!!!"
        for perm in self.require_permissions:
            if not self.request.user.has_perm(perm):
                return False
        allow = True
        if self.require_permissions_or:
            allow = False
            for perm in self.require_permissions_or:
                if self.request.user.has_perm(perm):
                    allow = True
        return allow
    
    def _check_apps(self):
        """ Check if this dashlet has the required apps installed for usage """
        for app in self.require_apps:
            if not app in settings.INSTALLED_APPS:
                return False
        return True
    
    def get_width(self):
        """ Get width in pixels for dashlet. Assuming 300px width and 20px gutters """
        return (self.columns * (300 + 20)) - 20
    

    def allow_usage(self):
        """ Public method to check if the user allowed to use this dashlet """
        if self._check_apps() and self._check_perm():
            return True
        return False

    def is_default(self):
        """ Should this dashlet be shown by default """
        return True


class AdminListDashlet(Dashlet):
    template_name = 'responsive_dashboard/admin_list_dashlet.html'
    app_label = None
    order = None
    models = ()
    models_exclude = ()
    
    def get_context_data(self):
        context = super(AdminListDashlet, self).get_context_data()
        app_list_url = urlresolvers.reverse('admin:app_list', args=(self.app_label,))
        content_types = ContentType.objects.filter(app_label=self.app_label)
        if self.models:
            content_types = content_types.filter(model__in=self.models)
        if self.models_exclude:
            content_types = content_types.exclude(model__in=self.models_exclude)
        
        for ct in content_types:
            try:
                if self.request.user.has_perm('{}.change_{}'.format(ct.app_label, ct.model)):
                    ct.change_url = urlresolvers.reverse('admin:{0}_{1}_changelist'.format(self.app_label, ct.model))
            except NoReverseMatch: # Probably no admin registered for this model
                pass
        context = dict(context.items() + {
            'content_types': content_types,
            'app_list_url': app_list_url,
        }.items())
        return context


class ListDashlet(Dashlet):
    """ Shows a list of data from a model """
    template_name = 'responsive_dashboard/list_dashlet.html'
    model = None
    fields = ('__str__',)
    queryset = None
    order_by = ()
    count = 5
    show_change = True
    show_add = False
    show_custom_link = None
    custom_link_text = None
    first_column_is_link = False
    allow_multiple = True
    extra_links = {}
    
    def get_context_data(self, **kwargs):
        context = super(ListDashlet, self).get_context_data(**kwargs)
        if self.queryset:
            object_list = self.queryset
        else:
            object_list = self.model.objects.all()
        
        if self.order_by:
            object_list = object_list.order_by(*self.order_by)
        
        object_list = object_list[:self.count]

        results = []
        for obj in object_list:
            result_row = []
            for field in self.fields:
                result_row += [getattr(obj, field)]
            obj.result_row = result_row
            results += [obj]
        
        headers = []
        for field in self.fields:
            if field == '__str__':
                headers += [self.model._meta.verbose_name]
            else:
                try:
                    if getattr(getattr(self.model, field, None), 'short_description', None):
                        headers += [getattr(getattr(self.model, field), 'short_description')]
                    else:
                        headers += [self.model._meta.get_field(field).verbose_name]
                except FieldDoesNotExist:
                    headers += [field]

        context = dict(context.items() + {
            'opts': self.model._meta,
            'object_list': object_list,
            'results': results,
            'headers': headers,
            'show_change': self.show_change,
            'show_add': self.show_add,
            'show_custom_link': self.show_custom_link,
            'custom_link_text': self.custom_link_text,
            'first_column_is_link': self.first_column_is_link,
            'extra_links': self.extra_links,
        }.items())
        return context


class LinksListDashlet(Dashlet):
    """ Shows a list of http links """
    template_name = "responsive_dashboard/links_list_dashlet.html"
    links = [
        {
            'text': 'Example Text',
            'link': 'http://www.example.com',
            'desc': "Description here",
            'perm': (), # List of permissions required for this link to show
            'required_apps': () # List of apps required for this link to show
        },
    ]

    def get_context_data(self, **kwargs):
        context = super(LinksListDashlet, self).get_context_data(**kwargs)
        active_links = []
        for link in self.links:
            add = True
            if 'perm' in link:
                for perm in link['perm']:
                    if not self.request.user.has_perm(perm):
                        add = False
            if 'required_apps' in link:
                for app in link['required_apps']:
                    if not app in settings.INSTALLED_APPS:
                        add = False
            if add:
                active_links += [link]
        
        context = dict(context.items() + {
            'links': active_links,
        }.items())
        return context


class RssFeedDashlet(Dashlet):
    feed_url = None
    more_link = None
    limit = 2

    def get_context_data(self, **kwargs):
        context = super(RssFeedDashlet, self).get_context_data(**kwargs)
        import datetime
        if self.feed_url is None:
            raise ValueError('You must provide a valid feed URL')
        import feedparser

        feed = feedparser.parse(self.feed_url)
        if self.limit is not None:
            entries = feed['entries'][:self.limit]
        else:
            entries = feed['entries']
        feed_lines = []
        for entry in entries:
            entry.url = entry.link
            try:
                entry.date = datetime.date(*entry.updated_parsed[0:3])
            except:
                # no date for certain feeds
                pass
            feed_lines.append(entry['summary_detail']['value'])
        context = dict(context.items() + {
            'list_items': feed_lines,
            'more_link': self.more_link,
        }.items())
        return context



responsive_dashboards = {}
# code from django-admin-tools THANKS!
# https://bitbucket.org/izi/django-admin-tools/src/e2732c0083c76862c7d014b7ab25d0dbd5e467c5/admin_tools/dashboard/registry.py
for app in settings.INSTALLED_APPS:
    # try to import the app
    try:
        app_path = import_module(app).__path__
    except AttributeError:
        continue

    # try to find a app.dashboard module
    try:
        imp.find_module('dashboards', app_path)
    except ImportError:
        continue

    # looks like we found it so import it !
    try: # TODO find a better way to make this work
        import_module('%s.dashboards' % app)
    except:
        pass
