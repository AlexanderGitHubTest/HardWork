# class check input data for correctness data and permissions
# for class based on model ReportVehicleMileageDuringPeriod
class ReportCheckInputDataCreateListUpdateRetrieve():
    def check_data(self, request, *args, **kwargs):
        def _is_user_authenticated(user):
            return user.is_authenticated and hasattr(user, 'user')
        def _is_vehicle_exist(vehicle):
            try:
                Vehicle.objects.get(id=vehicle)
            except ObjectDoesNotExist:
                return False
            return True
        def _is_enterprise_allowed(enterprises_allowed, vehicle):
            return enterprises_allowed.filter(id=vehicle.enterprise_id).exists()
        def _is_from_has_correct_format(from_date):
            try:
                date.fromisoformat(from_date)
            except Exception:
                return False
            return True
        def _is_to_has_correct_format(to_date):
            try:
                date.fromisoformat(to_date)
            except Exception:
                return False
            return True
        def _is_period_has_correct_format(period):
            return period in ['day', 'month', 'year']

        user = self.request.user
        verification_data = [
            {
                'name': 'check user',
                'check_function': _is_user_authenticated,
                'parameters': [self.request.user],
                'error_status': status.HTTP_401_UNAUTHORIZED,
                'error_message': f'User is not logged in.'
            },
            {
                'name': 'check vehicle',
                'check_function': _is_vehicle_exist,
                'parameters': [self.kwargs['vehicle']],
                'error_status': status.HTTP_404_NOT_FOUND,
                'error_message': f"Vehicle id {self.kwargs['vehicle']} does not exist."
            },
            {
                'name': 'enterprise allowed',
                'check_function': _is_enterprise_allowed,
                'parameters': [
                    Enterprise.objects.filter(enterprises__user_id=user.id),
                    Vehicle.objects.get(id=self.kwargs['vehicle'])
                ],
                'error_status': status.HTTP_403_FORBIDDEN,
                'error_message': f"Access to vehicle id {self.kwargs['vehicle']} reports is forbidden."
            },
            {
                'name': 'from has corrected format',
                'check_function': _is_from_has_correct_format,
                'parameters': [kwargs['from']],
                'error_status': status.HTTP_400_BAD_REQUEST,
                'error_message': ('Incorrect date format for the start of the trip selection.' +
                                  ' Correct format is ISO8601 (YYYY-MM-DD).'
                                  )
            },
            {
                'name': 'to has corrected format',
                'check_function': _is_to_has_correct_format,
                'parameters': [kwargs['to']],
                'error_status': status.HTTP_400_BAD_REQUEST,
                'error_message': ('Incorrect date format for the end of the trip selection.' +
                                  ' Correct format is ISO8601 (YYYY-MM-DD).'
                                  )
            },
            {
                'name': 'period has corrected format',
                'check_function': _is_period_has_correct_format,
                'parameters': [kwargs['period']],
                'error_status': status.HTTP_400_BAD_REQUEST,
                'error_message': ('Incorrect date format for the end of the trip selection.' +
                                  ' Correct format is ISO8601 (YYYY-MM-DD).'
                                  )
            }
        ]
        result = {'is_error': False,
                  'error_status': '',
                  'error_message': ''}

        for verification in verification_data:
            if not verification['check_function'](*verification['parameters']):
                result['is_error'] = True
                result['error_status'] = verification['error_status']
                result['error_message'] = verification['error_message']
                return result
        self.from_date = date.fromisoformat(kwargs['from'])
        self.to_date = date.fromisoformat(kwargs['to'])
        return result
      
