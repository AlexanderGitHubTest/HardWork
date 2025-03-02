# class check input data for correctness data and permissions
# for class based on model ReportVehicleMileageDuringPeriod
class ReportCheckInputDataCreateListUpdateRetrieve():
    def check_data(self, request, *args, **kwargs):
        result = {'is_error': False,
                  'error_status': '',
                  'error_message': ''}
        user = self.request.user
        if not user.is_authenticated or not hasattr(user, 'user'):
            result['is_error'] = True
            result['error_status'] = status.HTTP_401_UNAUTHORIZED
            result['error_message'] = f"User is not logged in."
            return result
        try:
            vehicle = Vehicle.objects.get(id=self.kwargs['vehicle'])
        except ObjectDoesNotExist:
            result['is_error'] = True
            result['error_status'] = status.HTTP_404_NOT_FOUND
            result['error_message'] = f"Vehicle id {self.kwargs['vehicle']} does not exist."
            return result
        enterprises_allowed = Enterprise.objects.filter(enterprises__user_id=user.id)
        if not enterprises_allowed.filter(id=vehicle.enterprise_id).exists():
            result['is_error'] = True
            result['error_status'] = status.HTTP_403_FORBIDDEN
            result['error_message'] = f"Access to vehicle id {self.kwargs['vehicle']} reports is forbidden."
            return result
        enterprise_time_zone = enterprises_allowed.get(id=vehicle.enterprise_id).time_zone
        try:
            self.from_date = date.fromisoformat(kwargs['from'])
        except Exception:
            result['is_error'] = True
            result['error_status'] = status.HTTP_400_BAD_REQUEST
            result['error_message'] = ('Incorrect date format for the start of the trip selection.' +
                                      ' Correct format is ISO8601 (YYYY-MM-DD).'
                                       )
            return result
        try:
            self.to_date = date.fromisoformat(kwargs['to'])
        except Exception:
            result['is_error'] = True
            result['error_status'] = status.HTTP_400_BAD_REQUEST
            result['error_message'] = ('Incorrect date format for the end of the trip selection.' +
                                       ' Correct format is ISO8601 (YYYY-MM-DD).'
                                       )
            return result
        if self.kwargs['period'] not in ['day', 'month', 'year']:
            result['is_error'] = True
            result['error_status'] = status.HTTP_400_BAD_REQUEST
            result['error_message'] = f"Period should be one of the values: day, month, year."
            return result
        return result
      
