import idle from "../assets/damian/idle.png";
import talk1 from "../assets/damian/talk_1.png";
import talk2 from "../assets/damian/talk_2.png";
import think1 from "../assets/damian/think_1.png";
import think2 from "../assets/damian/think_2.png";
import think3 from "../assets/damian/think_3.png";
import think4 from "../assets/damian/think_4.png";
import done from "../assets/damian/done.png";
import error from "../assets/damian/error.png";

const url = (image: string | { src: string }): string =>
  typeof image === "string" ? image : image.src;

export const damianSprites = {
  idle: [url(idle)],
  thinking: [url(think1), url(think2), url(think3), url(think4)],
  talking: [url(talk1), url(talk2)],
  done: [url(done)],
  error: [url(error)],
};

export type AvatarState = keyof typeof damianSprites;
