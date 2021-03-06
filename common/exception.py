#! coding: utf-8
import logging
import sys
from google.appengine.api import datastore_errors
from google.appengine.api import images
from django.conf import settings

NO_METHOD = 0x01
INVALID_METHOD = 0x02
OAUTH_ERROR = 0x03
PERMISSION_ERROR = 0x04
PRIVACY_ERROR = 0x05
INVALID_ARGUMENTS = 0x06
NOT_FOUND = 0x07
LOCKED = 0x08
THROTTLED = 0x09
ALREADY_IN_USE = 0x10


def handle_exception(request):
  exc_type, exc_value = sys.exc_info()[:2]
  if issubclass(exc_type, RedirectException):
    raise
  if issubclass(exc_type, datastore_errors.Error):
    log_exception()
    if not hasattr(request, 'errors'):
      request.errors = []
    request.errors.append(
        DatastoreError('There was an error communicating with the datastore'
                       ' please retry your last acton')
        )
  if issubclass(exc_type, UserVisibleError):
    logging.debug("UserVisibleError: %s" % exc_value)
    if not hasattr(request, 'errors'):
      request.errors = []
    request.errors.append(exc_value)
  else:
    raise

def handle_image_error(f, *args, **kw):
  """Catches app engine image errors and translates them to ApiException.
     f - function
     args - list of args to be passed to the function
     kw - dict of key-value args to be passed to the function
  """
  try:
    return f(*args, **kw)
  except images.LargeImageError:
    raise ApiException('Uploaded image size is too large')
  except images.NotImageError:
    raise ApiException('Uploaded image is not in a recognized image format')
  except images.Error:
    raise ApiException('Unable to process uploaded image')

def catch_api(*args):
  """catch an api exception of a specific type, re-raises if not matched"""
  exc_type, exc_value = sys.exc_info()[:2]
  if not issubclass(exc_type, Error):
    raise

  if exc_value.code in args:
    return exc_value
  else:
    raise

def log_exception():
  log_level = logging.ERROR
  if settings.MANAGE_PY:
    log_level = logging.DEBUG
  import traceback
  logging.log(log_level, "Error: %s", traceback.format_exc())

def log_warning():
  log_level = logging.WARNING
  if settings.MANAGE_PY:
    log_level = logging.DEBUG
  import traceback
  logging.log(log_level, "Warning: %s", traceback.format_exc())


# XXX andy: not used for the moment so that we can make this Python 2.4
#           compatible
class Catcher(object):
  def __init__(self, request):
    self.request = request
    if not hasattr(request, 'errors'):
      request.errors = []

  def __enter__(self):
    return None

  def __exit__(self, exc_type, exc_value, exc_tb):
    if isinstance(exc_type, Error):
      self.request.errors.append((exc_type, exc_value, exc_tb))
      return True
    return


class Error(Exception):
  @property
  def message(self):
    return "%s" % (self.__class__.__name__)

  def __str__(self):
    return self.message


class UserVisibleError(Error):
  """raised for errors that should be shown in the UI.
  
  Subclasses should implement to_html and to_api methods.
  """
  def to_html(self):
    raise NotImplementedError

  def to_api(self):
    raise NotImplementedError


class PrivateDataError(Error):
  """raised when a user tried to view another user's private data

  The user tried to view private data and must either be logged in or be a
  contact of the user to see it
  """
  # TODO should care about whether the user is logged in or not
  def __init__(self, view, current_user=None):
    self.view = view
    self.current_user = current_user


class UserDoesNotExistError(Error):
  def __init__(self, nick, current_user=None):
    self.nick = nick
    self.current_user = current_user

  @property
  def message(self):
    return u"Tài khoản %s không tồn tại." % self.nick.split("@")[0]

class DisabledFeatureError(UserVisibleError):
  # TODO(teemu): we should probably add an extra field 
  # for a user-friendly description of the disabled feature. 
  def to_html(self):
    return "This feature is disabled at the moment."

  def to_api(self):
    return "This feature is disabled at the moment."


class ValidationError(UserVisibleError):
  def __init__(self, user_message, field=None):
    self.user_message = user_message
    self.field = field

  def to_html(self):
    return self.user_message

  def to_api(self):
    return "%d:%d" % (self.field, self.user_message)

  def __str__(self):
    return self.user_message

class DatastoreError(ValidationError):
  pass

class ServiceError(ValidationError):
  """ the kind of error thrown when an external service tells us we're wrong """
  pass

class FeatureDisabledError(ValidationError):
  """ an error to raise when a feature has been disabled """
  pass

class RedirectException(Error):
  base_url = "/"
  redirect = False

  def build_redirect(self, request):
    return "%s?%s" % (request.META['PATH_INFO'], request.META['QUERY_STRING'])

  def build_url(self, request):
    # TODO(termie) rearrange these in the future to prevent circular imports
    from common import util
    base_url = self.base_url
    if self.redirect:
      redirect_to = self.build_redirect(request)
      base_url = util.qsa(base_url, {'redirect_to': redirect_to})
    return base_url


class ConfirmationRequiredException(RedirectException):
  base_url = "/confirm"
  redirect = True
  message = None

  def __init__(self, message):
    self.message = message

  def build_url(self, request):
    # TODO(termie) rearrange these in the future to prevent circular imports
    from common import util
    redirect_url = self.build_redirect(request)

    nonce = util.create_nonce(request.user, self.message + redirect_url)

    return util.qsa(self.base_url, {'message': self.message,
                                    '_nonce': nonce,
                                    'redirect_to': redirect_url})

  redirect = True


class GaeLoginRequiredException(RedirectException):
  redirect = True

  def build_url(self, request):
    from google.appengine.api import users
    url = users.create_login_url(request)
    return url


class LoginRequiredException(RedirectException):
  base_url = "/login"
  redirect = True


class AlreadyLoggedInException(RedirectException):
  def build_url(self, redirect_to=None):
    # TODO termie: should build an actor url
    return "/"


class ApiException(UserVisibleError):
  message = None
  code = 0x00

  def __init__(self, message=None, code=None):
    if code is not None:
      self.code = code
    if message is not None:
      self.message = message

  def to_dict(self):
    return dict(code=self.code, message=self.message)

  def __str__(self):
    return self.message

  def to_html(self):
    return self.message

  def to_api(self):
    return self.to_dict()

class ApiNotFound(ApiException):
  code = NOT_FOUND

class ApiDeleted(ApiNotFound):
  pass

class ApiLocked(ApiException):
  code = LOCKED

class ApiNoTasks(ApiNotFound):
  pass

class ApiThrottled(ApiException):
  code = THROTTLED

class ApiPermissionDenied(ApiException):
  code = PERMISSION_ERROR

class ApiOwnerRequired(ApiException):
  code = PRIVACY_ERROR

class ApiViewableRequired(ApiException):
  code = PRIVACY_ERROR

class ApiNoMethod(ApiException):
  code = NO_METHOD

class ApiInvalidMethod(ApiException):
  code = INVALID_METHOD

class ApiInvalidArguments(ApiException):
  code = INVALID_ARGUMENTS

class ApiOAuth(ApiException):
  code = OAUTH_ERROR


class ApiAlreadyInUse(ApiException):
  code = ALREADY_IN_USE
