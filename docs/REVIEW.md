1. Auth: does every new route depend on get_current_user? Any path that authenticates without a verified token?
2. Data isolation: any service-role query without a user filter? Test with two users?
3. Disclaimer: does every generated carousel, image and video still include compliance/disclaimer.py text? Was that file touched?
4. Carousel template: any change to swipeable_carousel.py layout, spacing or colours not requested in the task file?
5. Secrets: keys in code, logs or error messages? Frontend using anything but the publishable key?
6. Tests: do they mock every external API? Meaningful assertions? Any test weakened?
7. Vendored files untouched?
8. New dependencies approved and pinned?
9. Error handling: user-facing messages clean; failures logged with context.
10. Scope: only what the task file asked?
