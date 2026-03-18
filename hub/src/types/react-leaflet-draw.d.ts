declare module 'react-leaflet-draw' {
  import * as React from 'react';

  export interface EditControlProps {
    position?: string;
    onCreated?: (e: any) => void;
    onEdited?: (e: any) => void;
    onDeleted?: (e: any) => void;
    draw?: {
      rectangle?: boolean | object;
      polygon?: boolean | object;
      circle?: boolean | object;
      polyline?: boolean | object;
      marker?: boolean | object;
      circlemarker?: boolean | object;
    };
    edit?: {
      edit?: boolean | object;
      remove?: boolean | object;
    };
  }

  export const EditControl: React.FC<EditControlProps>;
}
