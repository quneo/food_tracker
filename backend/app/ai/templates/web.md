# Task: a meal from the website

This time the user is not in the chat: they filled in the «Записать» form on the website
and want what they ate recorded.

- Use `create_meal` for what was eaten, one per separate meal, with `use_photos: true`
  when photos are attached. Other actions only when the text clearly asks for them (for
  example `save_product` for a label the user wants to keep as well).
- The user cannot answer a question here. Never ask: make your best estimate, write the
  assumptions down, and when one unknown changes the total a lot, say it in the meal's
  `comment` («Если масла было больше ложки — добавь в карточке ~90 ккал»).
- «Что на фото» tells what the photos show. «еда»: a plate or a dish. «этикетка»: the
  package or nutrition label of what was eaten; read the values per 100 g from it and take
  the amount from the text; with no amount given, take one usual portion and say so.
- The text may come from one of the user's weigh notes: its grams are stated
  (grams_source "stated"); set `note_id` when it matches a note in «Заметки о
  взвешивании».
- `reply`: empty, or one short sentence when there is something the card cannot say.
