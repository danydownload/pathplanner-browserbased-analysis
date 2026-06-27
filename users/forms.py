from django import forms
from .models import UserProfile, UserPreferences
import re

# Form for viewing/editing your profile
class UserProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ['first_name', 'last_name', 'email', 'profile_picture', 'default_pathology']

        labels = {
            'first_name': 'First name',
            'last_name': 'Last name',
            'email': 'Email',
            'profile_picture': 'Profile picture',
            'preferences': 'Preferences',
            'default_pathology': 'Default clinical condition',
        }

        help_texts = {
            'default_pathology': 'This condition is pre-selected when you plan a route.',
        }

        widgets = {
            'default_pathology': forms.RadioSelect(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set fields as non-compulsory
        self.fields['first_name'].required = False
        self.fields['last_name'].required = False
        self.fields['email'].required = False
        self.fields['profile_picture'].required = False
        self.fields['default_pathology'].required = False

        # Friendly placeholders
        self.fields['first_name'].widget.attrs['placeholder'] = 'Your first name'
        self.fields['last_name'].widget.attrs['placeholder'] = 'Your last name'
        self.fields['email'].widget.attrs['placeholder'] = 'your.email@example.com'
        self.fields['email'].disabled = True
        self.fields['email'].help_text = 'Email changes are disabled for now. Password/email reset will be added separately.'
        self.fields['profile_picture'].help_text = 'Upload a square image if possible; it will be cropped into a circular avatar.'

    # Method for checking the name
    def clean_first_name(self): 
        first_name = self.cleaned_data['first_name']
        if re.search(r'\d', first_name):
            raise forms.ValidationError("The name may not contain numbers.")
        return first_name

     # Method for checking the surname
    def clean_last_name(self):
        last_name = self.cleaned_data['last_name']
        if re.search(r'\d', last_name):
            raise forms.ValidationError("The surname may not contain numbers.")
        return last_name

    def clean_email(self):
        if self.instance and getattr(self.instance, 'user', None):
            return self.instance.user.email
        return self.cleaned_data.get('email', '')


# Form to display a user's preferences and allow them to modify it
class UserPreferencesForm(forms.ModelForm):
    class Meta:
        model = UserPreferences
        fields = [
            'name', 
            'nature',
            'entertainment',
            'tourism',
            'nightlife',
            'hospital'
        ]

        labels = {
            'name': 'Name',
            'nature': 'Parks and green areas',
            'entertainment': 'Entertainment',
            'tourism': 'Tourism and landmarks',
            'nightlife': 'Nightlife',
            'hospital': 'Medical access'
        }
        
        widgets = {
            'nature': forms.NumberInput(attrs={'type': 'range', 'min': 0, 'max': 10, 'step': 1, 'id': 'id_nature'}),
            'entertainment': forms.NumberInput(attrs={'type': 'range', 'min': 0, 'max': 10, 'step': 1, 'id': 'id_entertainment'}),
            'tourism': forms.NumberInput(attrs={'type': 'range', 'min': 0, 'max': 10, 'step': 1, 'id': 'id_tourism'}),
            'nightlife': forms.NumberInput(attrs={'type': 'range', 'min': 0, 'max': 10, 'step': 1, 'id': 'id_nightlife'}),
            'hospital': forms.NumberInput(attrs={'type': 'range', 'min': 0, 'max': 10, 'step': 1, 'id': 'id_hospital'}),
        }
