from django.contrib import admin
from .models import Author, Following

class AuthorAdmin(admin.ModelAdmin):
    # Specify the fields to display in the list view
    list_display = ('displayName', 'email', 'isVerified', 'isNode')  # Add more fields as needed
    # Allow admins to edit isVerified and isNode directly from the list view
    list_editable = ('isVerified', 'isNode')
    # Enable search functionality
    search_fields = ('displayName', 'email')  
    # Allow filtering by isVerified status
    list_filter = ('isVerified',)
    # Optional: Add ordering by displayName
    ordering = ('displayName',)

# Register the Author model with the customized admin interface
admin.site.register(Author, AuthorAdmin)

# Register Following model as is
admin.site.register(Following)
