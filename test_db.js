require('dotenv').config();
const { createClient } = require('@supabase/supabase-js');

const supabase = createClient(
  process.env.REACT_APP_SUPABASE_URL,
  process.env.REACT_APP_SUPABASE_ANON_KEY
);

async function run() {
  const { data, error } = await supabase.from('dashboard_returns').select('*').limit(1);
  if (error) console.error(error);
  else console.log("Sample dashboard_returns row:", JSON.stringify(data[0], null, 2));
}

run();
