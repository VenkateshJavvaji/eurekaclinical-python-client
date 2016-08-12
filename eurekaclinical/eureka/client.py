import cookielib, requests
from contextlib import contextmanager
import json

_cookie_jar = cookielib.CookieJar()

class CASServer(object):
    def __init__(self, cas_url, verify_cert=True):
        self.__cas_url = cas_url
        self.__ticket_url = cas_url + '/v1/tickets/'
        self.__verify_cert = verify_cert

    def login(self, username, password):
        params = {'username': username, 'password': password}
        result = requests.post(self.__ticket_url, data=params, verify=self.__verify_cert)
        result.raise_for_status()
        location = result.headers['Location']
        self.__tgt = location[location.rfind('/') + 1:]

    def get_service_ticket(self, service):
        params = {'service': service}
        result = requests.post(self.__ticket_url + self.__tgt, data=params, verify=self.__verify_cert)
        result.raise_for_status()
        return result.text

    def logout(self):
        requests.delete(self.__ticket_url + self.__tgt, verify=self.__verify_cert)

class Struct(object):
    def __init__(self, data=None):
        super(Struct, self).__init__()
        if data is not None:
            for name, value in data.iteritems():
                setattr(self, name, self.__wrap(value))

    def to_json(self):
        def json_dumps_default(o):
            return {key: \
                    json_dumps_default(value) if hasattr(value, '__dict__') else value \
                    for key, value in o.__dict__.iteritems()}
        return json.dumps(self, default=json_dumps_default)

    def __wrap(self, value):
        if isinstance(value, (tuple, list, set, frozenset)): 
            return type(value)([self._wrap(v) for v in value])
        else:
            return Struct(value) if isinstance(value, dict) else value

class Job(Struct):
    def __init__(self):
        super(Job, self).__init__()
        self.sourceConfigId = None
        self.destinationId = None
        self.dateRangePhenotypeKey = None
        self.earliestDate = None
        self.earliestDateSide = 'START'
        self.latestDate = None
        self.latestDateSide = 'START'
        self.updateData = False
        self.prompts = None
        self.propositionIds = []
        self.name = None

class API(object):
    def __init__(self, rest_endpoint, cas, verify_cert, api_url):
        self.__cas = cas
        self.__verify_cert = verify_cert
        self.__api_url = api_url
        self.rest_endpoint = rest_endpoint

    def get(self, id):
        return self._get(self.rest_endpoint + str(id))

    def all(self):
        return self._get(self.rest_endpoint)
    
    def _get(self, rest_endpoint):
        url = self.__api_url +  '/proxy-resource' + rest_endpoint
        result = requests.get(url, cookies=_cookie_jar, verify=self.__verify_cert)
        result.raise_for_status()
        return self._loads(result)

    def _post(self, rest_endpoint, o):
        url = self.__api_url + '/proxy-resource' + rest_endpoint
        result = requests.post(url, data=o.to_json(), cookies=_cookie_jar, verify=self.__verify_cert)
        result.raise_for_status()
        return result.headers['Location']

    @staticmethod
    def _loads(result):
        return json.loads(result.text, object_hook=lambda d: Struct(d))
            
class Users(API):
    def __init__(self, *args, **kwargs):
        super(Users, self).__init__('/users/', *args, **kwargs)

    def me(self):
        return self._get(self.rest_endpoint + "me")

class Phenotypes(API):
    def __init__(self, *args, **kwargs):
        super(Phenotypes, self).__init__('/phenotypes/', *args, **kwargs)

class Concepts(API):
    def __init__(self, *args, **kwargs):
        super(Concepts, self).__init__('/concepts/', *args, **kwargs)

    def get(self, key, summarize=False):
        return self._get(self.rest_endpoint + key + "?summarize=" + str(summarize))

class Jobs(API):
    def __init__(self, *args, **kwargs):
        super(Jobs, self).__init__('/jobs/', *args, **kwargs)

    def submit(self, job):
        return self._post(self.rest_endpoint, job)
    
class Eureka(object):
    def __init__(self, username, password,
                 cas_url='https://localhost:8443/cas-server', verify_cas_cert=True,
                 api_url='https://localhost:8443/eureka-webapp', verify_api_cert=True):
        self.__verify_cas_cert = verify_cas_cert
        self.__verify_api_cert = verify_api_cert
        self.__cas = CASServer(cas_url, verify_cas_cert)
        self.__cas.login(username, password)
        self.__api_url = api_url
        self.__get_cookie()
        self.__api_args = (self.__cas, self.__verify_api_cert, self.__api_url)

    def users(self):
        return Users(*self.__api_args)

    def phenotypes(self):
        return Phenotypes(*self.__api_args)

    def concepts(self):
        return Concepts(*self.__api_args)

    def jobs(self):
        return Jobs(*self.__api_args)
    
    def close(self):
        self.__cas.logout()

    def __get_cookie(self):
        get_cookie_url = "/protected/user_acct"
        url = self.__api_url + get_cookie_url + "?ticket=" + self.__cas.get_service_ticket(self.__api_url + get_cookie_url)
        requests.get(url, cookies=_cookie_jar, verify=self.__verify_api_cert)

@contextmanager
def connect(*args, **kwargs):
    eureka = None
    try:
        eureka = Eureka(*args, **kwargs)
        yield eureka
    finally:
        try:
            close_it = eureka.close
        except AttributeError:
            pass
        else:
            close_it()

