#! coding: utf-8
from django import http
from django import template
from django.conf import settings
from django.template import loader
from django.core.cache import cache
from common import api
from common import clean
from common import decorator
from common import exception
from common import user
from common import util
from common import views as common_views

@decorator.cache_never
def login_login(request):
  green_title = True
  title = "Đăng nhập"
  redirect_to = request.REQUEST.get('redirect_to', '/')
  redirect_to = clean.redirect_to(redirect_to)

  if request.POST:
    try:
      login = request.POST.get('log', None)
      password = request.POST.get('pwd', None)
      rememberme = request.POST.get('rememberme', None)

      # TODO validate

      current_user = user.lookup_user_by_login(login, password)
      if current_user:
        if redirect_to == '/':
          redirect_to = current_user.url('/unread_messages')

        # Attempt to do some cleanup on the user if necessary
        api.user_cleanup(api.ROOT, current_user.nick)


        # if we aren't hosted or aren't ssl just set the cookie and go home
        if (not settings.HOSTED_DOMAIN_ENABLED
            or not settings.SSL_LOGIN_ENABLED):
          response = http.HttpResponseRedirect(redirect_to)
          response = user.set_user_cookie(response, current_user, rememberme)
          return response

        # otherwise, we're going to have to redirect to set the cookie on
        # the proper domain
        sso_token = util.generate_uuid()

        cache.set('sso/%s' % sso_token, (current_user.nick, rememberme), timeout=10)
        sso_url = 'http://%s/login/noreally' % (settings.DOMAIN)
        sso_url = util.qsa(
            sso_url, {'redirect_to': redirect_to, 'sso_token': sso_token})
        return http.HttpResponseRedirect(sso_url)
      else:
        raise exception.ValidationError(u"Tên đăng nhập / mật khẩu không hợp lệ")
    except:
      exception.handle_exception(request)

  if request.user:
    if redirect_to == '/':
      redirect_to = request.user.url('/overview')
    return http.HttpResponseRedirect(redirect_to)

  c = template.RequestContext(request, locals())
  t = loader.get_template('login/templates/login.html')
  return http.HttpResponse(t.render(c))

@decorator.cache_never
def login_noreally(request):
  if 'sso_token' in request.GET:
    sso_token = request.GET['sso_token']
    redirect_to = request.GET['redirect_to']
    redirect_to = clean.redirect_to(redirect_to)

    nick, rememberme = cache.get('sso/%s' % sso_token)
    cache.delete('sso/%s' % sso_token)
    actor_ref = api.actor_get(api.ROOT, nick)
    response = http.HttpResponseRedirect(redirect_to)
    response = user.set_user_cookie(response, actor_ref, rememberme)
    return response
  return http.HttpResponseRedirect('/login')

@decorator.cache_never
def login_logout(request):
  green_title = True
  title = "Đăng xuất"
  request.user = None
  redirect_to = '/'
  c = template.RequestContext(request, locals())
  t = loader.get_template('login/templates/logout.html')

  response = http.HttpResponse(t.render(c))
  response = user.clear_user_cookie(response)
  return response

def login_forgot(request):
  green_title = True
  title = "Quên mật khẩu"
  if request.user:
    # If the user is logged in, they don't get to the "forgot password" page.
    raise exception.AlreadyLoggedInException()

  handled = common_views.handle_view_action(
      request, {'login_forgot': request.path, })

  if handled:
    return handled

  c = template.RequestContext(request, locals())
  t = loader.get_template('login/templates/forgot.html')

  response = http.HttpResponse(t.render(c))
  return response

def login_reset(request):
  green_title = True
  title = "Khôi phục mật khẩu"
  # TODO(termie): this is a weird return type for an api call
  new_password, nick = api.login_reset(
      None, request.GET.get('email'), request.GET.get('hash'))

  c = template.RequestContext(request, locals())
  t = loader.get_template('login/templates/recover.html')

  response = http.HttpResponse(t.render(c))
  return response
